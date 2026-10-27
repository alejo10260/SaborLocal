"""
app.py
------
Versión WEB de SaborLocal (Flask + MongoDB), reutilizando core/ y services/.
Roles: CLIENTE y CHEF (se eliminó el rol administrador).

Ejecutar con:  python app.py
Luego abrir:   http://127.0.0.1:5000
"""

import functools

from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify

from core.dtos import UserRegistrationDTO, ChefRegistrationDTO
from services.auth_service import AuthService, AuthError
from services.restaurant_service import RestaurantService, RestaurantError
from services.order_service import OrderService, OrderError
from services.payment_service import PaymentService, PaymentError
from services.review_service import ReviewService, ReviewError

app = Flask(__name__)
app.secret_key = "saborlocal-web-dev-secret"  # solo para firmar la cookie de sesión de Flask

ESTADOS_LEGIBLES = {
    "PENDIENTE_CHEF": ("Esperando confirmación del restaurante", "warning"),
    "RECHAZADO": ("Rechazado por el restaurante", "danger"),
    "PAGADO": ("Pagado — en cola de preparación", "info"),
    "EN_PREPARACION": ("En preparación", "info"),
    "EN_TRANSITO": ("En camino", "info"),
    "LISTO_PARA_RECOGER": ("Listo para recoger", "info"),
    "COMPLETADO": ("Completado", "success"),
}

# ---------------------------------------------------------------------
# Helpers de sesión / autorización
# ---------------------------------------------------------------------
def usuario_actual():
    return session.get("usuario")


def requiere_login(rol=None):
    def decorador(vista):
        @functools.wraps(vista)
        def envoltura(*args, **kwargs):
            usuario = usuario_actual()
            if usuario is None:
                flash("Debes iniciar sesión para continuar.", "warning")
                return redirect(url_for("login"))
            if rol and usuario["rol"] != rol:
                flash("No tienes permiso para acceder a esa sección.", "danger")
                return redirect(url_for("index"))
            return vista(*args, **kwargs)
        return envoltura
    return decorador


@app.context_processor
def inyectar_globales():
    return {"usuario": usuario_actual(), "estados_legibles": ESTADOS_LEGIBLES}


def cantidad_en_carrito(producto_id):
    return sum(i["cantidad"] for i in session.get("carrito", []) if i["producto_id"] == producto_id)


# ---------------------------------------------------------------------
# Home
# ---------------------------------------------------------------------
@app.route("/")
def index():
    usuario = usuario_actual()
    if usuario is None:
        return redirect(url_for("login"))
    destino = {"CLIENTE": "panel_cliente", "CHEF": "panel_chef"}
    return redirect(url_for(destino[usuario["rol"]]))


# ---------------------------------------------------------------------
# HU-01/02/03/04: autenticación
# ---------------------------------------------------------------------
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        try:
            resultado = AuthService().iniciar_sesion(
                request.form.get("correo", "").strip(), request.form.get("contrasena", "")
            )
            session["usuario"] = resultado["usuario"]
            session["token"] = resultado["token"]
            session.setdefault("carrito", [])
            return redirect(url_for("index"))
        except AuthError as e:
            flash(str(e), "danger")
    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.route("/registro/cliente", methods=["GET", "POST"])
def registro_cliente():
    if request.method == "POST":
        dto = UserRegistrationDTO(
            nombre=request.form.get("nombre", ""),
            correo_electronico=request.form.get("correo", "").strip(),
            contrasena=request.form.get("contrasena", ""),
        )
        try:
            AuthService().registrar_cliente(dto)
            flash("Cuenta creada. Ahora puedes iniciar sesión.", "success")
            return redirect(url_for("login"))
        except AuthError as e:
            flash(str(e), "danger")
    return render_template("registro_cliente.html")


@app.route("/registro/chef", methods=["GET", "POST"])
def registro_chef():
    if request.method == "POST":
        dto = ChefRegistrationDTO(
            nombre=request.form.get("nombre", ""),
            correo_electronico=request.form.get("correo", "").strip(),
            contrasena=request.form.get("contrasena", ""),
            nombre_restaurante=request.form.get("nombre_restaurante", ""),
            direccion=request.form.get("direccion", ""),
            descripcion=request.form.get("descripcion", ""),
        )
        try:
            AuthService().registrar_chef(dto)
            flash("Restaurante registrado. Inicia sesión para configurar tu menú y publicarlo.", "success")
            return redirect(url_for("login"))
        except AuthError as e:
            flash(str(e), "danger")
    return render_template("registro_chef.html")


# ---------------------------------------------------------------------
# CLIENTE
# ---------------------------------------------------------------------
@app.route("/cliente")
@requiere_login("CLIENTE")
def panel_cliente():
    restaurantes = RestaurantService().listar_restaurantes_publicados()
    return render_template("cliente_explorar.html", restaurantes=restaurantes)


@app.route("/cliente/restaurante/<int:restaurante_id>")
@requiere_login("CLIENTE")
def cliente_restaurante(restaurante_id):
    servicio = RestaurantService()
    productos = servicio.listar_productos(restaurante_id)
    restaurante = next((r for r in servicio.listar_restaurantes_publicados()
                         if r["id"] == restaurante_id), None)
    en_carrito = {p["id"]: cantidad_en_carrito(p["id"]) for p in productos}
    return render_template("cliente_menu.html", productos=productos, restaurante=restaurante,
                            restaurante_id=restaurante_id, en_carrito=en_carrito)


@app.route("/cliente/carrito/agregar", methods=["POST"])
@requiere_login("CLIENTE")
def carrito_agregar():
    restaurante_id = int(request.form["restaurante_id"])
    producto_id = int(request.form["producto_id"])
    try:
        cantidad = max(1, int(request.form.get("cantidad", 1)))
    except ValueError:
        cantidad = 1
    volver = redirect(url_for("cliente_restaurante", restaurante_id=restaurante_id))

    producto = RestaurantService().obtener_producto(producto_id)
    if producto is None or producto["restaurante_id"] != restaurante_id:
        flash("Ese producto ya no está disponible.", "danger")
        return volver

    carrito = session.get("carrito", [])
    if carrito and carrito[0]["restaurante_id"] != restaurante_id:
        flash("Ya tienes productos de otro restaurante en el carrito. Vacíalo antes de agregar de otro.", "warning")
        return volver

    ya_en_carrito = cantidad_en_carrito(producto_id)
    disponible = producto["inventario"] - ya_en_carrito
    if disponible <= 0:
        flash(f"No hay más unidades de '{producto['nombre']}' disponibles"
              + (" (ya tienes todo el stock en tu carrito)." if ya_en_carrito else "."), "warning")
        return volver
    if cantidad > disponible:
        flash(f"Solo puedes agregar {disponible} unidad(es) más de '{producto['nombre']}'. "
              f"Se agregó el máximo disponible.", "warning")
        cantidad = disponible

    for item in carrito:
        if item["producto_id"] == producto_id:
            item["cantidad"] += cantidad
            break
    else:
        carrito.append({"restaurante_id": restaurante_id, "producto_id": producto_id,
                         "nombre": producto["nombre"], "precio": producto["precio"], "cantidad": cantidad})
    session["carrito"] = carrito
    flash(f"'{producto['nombre']}' agregado al carrito.", "success")
    return volver


@app.route("/cliente/carrito/quitar/<int:producto_id>", methods=["POST"])
@requiere_login("CLIENTE")
def carrito_quitar(producto_id):
    session["carrito"] = [i for i in session.get("carrito", []) if i["producto_id"] != producto_id]
    return redirect(url_for("carrito_ver"))


@app.route("/cliente/carrito/actualizar/<int:producto_id>", methods=["POST"])
@requiere_login("CLIENTE")
def carrito_actualizar(producto_id):
    try:
        nueva_cantidad = int(request.form.get("cantidad", 1))
    except (TypeError, ValueError):
        nueva_cantidad = 1

    if nueva_cantidad <= 0:
        session["carrito"] = [i for i in session.get("carrito", []) if i["producto_id"] != producto_id]
        return redirect(url_for("carrito_ver"))

    producto = RestaurantService().obtener_producto(producto_id)
    if producto is None:
        flash("Ese producto ya no está disponible; se quitó del carrito.", "warning")
        session["carrito"] = [i for i in session.get("carrito", []) if i["producto_id"] != producto_id]
        return redirect(url_for("carrito_ver"))
    if nueva_cantidad > producto["inventario"]:
        flash(f"Solo hay {producto['inventario']} unidades disponibles de '{producto['nombre']}'.", "warning")
        nueva_cantidad = max(1, producto["inventario"])

    carrito = session.get("carrito", [])
    for item in carrito:
        if item["producto_id"] == producto_id:
            item["cantidad"] = nueva_cantidad
            break
    session["carrito"] = carrito
    return redirect(url_for("carrito_ver"))


@app.route("/cliente/carrito")
@requiere_login("CLIENTE")
def carrito_ver():
    carrito = session.get("carrito", [])
    total = round(sum(i["precio"] * i["cantidad"] for i in carrito), 2)
    return render_template("cliente_carrito.html", carrito=carrito, total=total)


@app.route("/cliente/checkout", methods=["POST"])
@requiere_login("CLIENTE")
def checkout():
    carrito = session.get("carrito", [])
    if not carrito:
        flash("Tu carrito está vacío.", "warning")
        return redirect(url_for("panel_cliente"))

    tipo_entrega = request.form.get("tipo_entrega", "DOMICILIO")
    direccion = request.form.get("direccion", "")
    try:
        RestaurantService.validar_tipo_entrega(tipo_entrega, direccion)
        carrito_items = [{"producto_id": i["producto_id"], "cantidad": i["cantidad"]} for i in carrito]
        pedido_id = OrderService().crear_pedido(
            cliente_id=usuario_actual()["id"],
            restaurante_id=carrito[0]["restaurante_id"],
            carrito=carrito_items,
            tipo_entrega=tipo_entrega,
            direccion_entrega=direccion if tipo_entrega == "DOMICILIO" else None,
        )
        session["carrito"] = []
        flash(f"Pedido #{pedido_id} creado. Espera a que el restaurante lo confirme.", "success")
        return redirect(url_for("cliente_pedidos"))
    except (RestaurantError, OrderError) as e:
        flash(str(e), "danger")
        return redirect(url_for("carrito_ver"))


@app.route("/cliente/pedidos")
@requiere_login("CLIENTE")
def cliente_pedidos():
    ordenes = OrderService()
    pedidos = ordenes.listar_pedidos_de_cliente(usuario_actual()["id"])
    aceptados = {p["id"]: ordenes.pedido_fue_aceptado(p["id"]) for p in pedidos}
    calificados = {p["id"]: ReviewService().pedido_calificado(p["id"]) for p in pedidos}
    return render_template("cliente_pedidos.html", pedidos=pedidos, aceptados=aceptados, calificados=calificados)


@app.route("/cliente/pedido/<int:pedido_id>/pagar", methods=["GET", "POST"])
@requiere_login("CLIENTE")
def cliente_pagar(pedido_id):
    if request.method == "POST":
        tipo_pago = request.form.get("tipo_pago")
        campos = {
            "numero_tarjeta": request.form.get("numero_tarjeta", ""),
            "fecha_expiracion": request.form.get("fecha_expiracion", ""),
            "cvv": request.form.get("cvv", "")
        }
        try:
            cabecera, _ = OrderService().detalle_pedido(pedido_id)
            resultado = PaymentService.procesar_pasarela(
                pedido_id=pedido_id, 
                tipo_pago=tipo_pago, 
                datos_tarjeta=campos, 
                monto_total=cabecera["monto_total"]
            )
            
            if not resultado.get("exito"):
                flash(resultado.get("mensaje"), "danger")
            else:
                # Actualizar a PAGADO en base de datos
                OrderService().marcar_como_pagado(pedido_id)
                flash(f"¡Pago aprobado! Transacción {resultado.get('transaccion_id')}.", "success")
                return redirect(url_for("cliente_recibo", pedido_id=pedido_id))
        except Exception as e:
            flash(str(e), "danger")
            
    cabecera, detalles = OrderService().detalle_pedido(pedido_id)
    return render_template("cliente_pagar.html", pedido=cabecera, detalles=detalles)


@app.route("/cliente/pedido/<int:pedido_id>/recibo")
@requiere_login("CLIENTE")
def cliente_recibo(pedido_id):
    # Ya que no guardamos en DB el recibo en la pasarela mock, pasaremos los datos del pedido
    cabecera, detalles = OrderService().detalle_pedido(pedido_id)
    return render_template("cliente_recibo.html", recibo=cabecera, pedido_id=pedido_id)


@app.route("/cliente/pedido/<int:pedido_id>/confirmar", methods=["POST"])
@requiere_login("CLIENTE")
def cliente_confirmar(pedido_id):
    try:
        OrderService().confirmar_recepcion(pedido_id, usuario_actual()["id"])
        flash("Recepción confirmada. ¡Buen provecho!", "success")
    except OrderError as e:
        flash(str(e), "danger")
    return redirect(url_for("cliente_pedidos"))


@app.route("/cliente/pedido/<int:pedido_id>/calificar", methods=["POST"])
@requiere_login("CLIENTE")
def cliente_calificar(pedido_id):
    try:
        ReviewService().calificar_pedido(
            pedido_id, usuario_actual()["id"],
            int(request.form.get("puntuacion", 5)), request.form.get("comentario", ""),
        )
        flash("¡Gracias por tu calificación!", "success")
    except ReviewError as e:
        flash(str(e), "danger")
    return redirect(url_for("cliente_pedidos"))


# ---------------------------------------------------------------------
# CHEF
# ---------------------------------------------------------------------
@app.route("/chef")
@requiere_login("CHEF")
def panel_chef():
    restaurante = RestaurantService().obtener_restaurante_por_usuario(usuario_actual()["id"])
    pedidos, aceptados, detalles = [], {}, {}
    if restaurante and restaurante["estado"] == "PUBLICADO":
        ordenes = OrderService()
        pedidos = ordenes.listar_pedidos_de_chef(restaurante["id"])
        aceptados = {p["id"]: ordenes.pedido_fue_aceptado(p["id"]) for p in pedidos}
        detalles = {p["id"]: ordenes.detalle_pedido(p["id"])[1] for p in pedidos}
    return render_template("chef_panel.html", restaurante=restaurante, pedidos=pedidos,
                            aceptados=aceptados, detalles=detalles)


@app.route("/chef/menu", methods=["GET", "POST"])
@requiere_login("CHEF")
def chef_menu():
    servicio = RestaurantService()
    usuario_id = usuario_actual()["id"]
    restaurante = servicio.obtener_restaurante_por_usuario(usuario_id)
    borrador = session.get("borrador_platillos", [])

    if request.method == "POST":
        accion = request.form.get("accion")
        try:
            if accion == "agregar_platillo":
                precio = float(request.form.get("precio", 0))
                inventario = int(request.form.get("inventario", 0))
                if precio <= 0:
                    raise ValueError("El precio debe ser mayor a 0.")
                if inventario < 0:
                    raise ValueError("El inventario no puede ser negativo.")
                borrador.append({
                    "nombre": request.form.get("nombre_platillo", ""),
                    "descripcion": request.form.get("descripcion_platillo", ""),
                    "precio": precio, "inventario": inventario,
                })
                session["borrador_platillos"] = borrador
                flash("Platillo agregado a la lista (aún no publicado).", "success")

            elif accion == "quitar_platillo":
                idx = int(request.form.get("indice"))
                if 0 <= idx < len(borrador):
                    borrador.pop(idx)
                session["borrador_platillos"] = borrador

            elif accion == "publicar":
                servicio.configurar_perfil_y_menu(
                    usuario_id=usuario_id,
                    nombre=request.form.get("nombre_restaurante", ""),
                    direccion=request.form.get("direccion", ""),
                    descripcion=request.form.get("descripcion", ""),
                    hora_apertura=request.form.get("hora_apertura", ""),
                    hora_cierre=request.form.get("hora_cierre", ""),
                    platillos=borrador,
                )
                session["borrador_platillos"] = []
                flash("¡Restaurante publicado! Ya aparece en el catálogo de clientes.", "success")
                return redirect(url_for("panel_chef"))

            elif accion == "actualizar_perfil":
                servicio.actualizar_perfil(
                    usuario_id, request.form.get("nombre_restaurante", ""),
                    request.form.get("direccion", ""), request.form.get("descripcion", ""),
                    request.form.get("hora_apertura", ""), request.form.get("hora_cierre", ""),
                )
                flash("Perfil del restaurante actualizado.", "success")

            elif accion == "agregar_platillo_publicado":
                servicio.agregar_platillo(
                    usuario_id, request.form.get("nombre_platillo", ""),
                    request.form.get("descripcion_platillo", ""),
                    float(request.form.get("precio", 0)), int(request.form.get("inventario", 0)),
                )
                flash("Platillo agregado al menú publicado.", "success")

            elif accion == "quitar_publicado":
                servicio.quitar_producto(int(request.form.get("producto_id")), usuario_id)
                flash("Platillo retirado del menú.", "info")
        except (RestaurantError, ValueError) as e:
            flash(str(e), "danger")
        return redirect(url_for("chef_menu"))

    menu_publicado = []
    if restaurante and restaurante["estado"] == "PUBLICADO":
        menu_publicado = servicio.listar_productos(restaurante["id"])
    return render_template("chef_menu.html", restaurante=restaurante, borrador=borrador,
                            menu_publicado=menu_publicado)


@app.route("/chef/producto/<int:producto_id>/editar", methods=["GET", "POST"])
@requiere_login("CHEF")
def chef_editar_producto(producto_id):
    servicio = RestaurantService()
    try:
        producto = servicio.obtener_producto_de_chef(producto_id, usuario_actual()["id"])
    except RestaurantError as e:
        flash(str(e), "danger")
        return redirect(url_for("chef_menu"))

    if request.method == "POST":
        try:
            servicio.actualizar_producto(
                producto_id=producto_id, usuario_id=usuario_actual()["id"],
                nombre=request.form.get("nombre", ""), descripcion=request.form.get("descripcion", ""),
                precio=float(request.form.get("precio", 0)), inventario=int(request.form.get("inventario", 0)),
            )
            flash("Platillo actualizado.", "success")
            return redirect(url_for("chef_menu"))
        except (RestaurantError, ValueError) as e:
            flash(str(e), "danger")
    return render_template("chef_editar_producto.html", producto=producto)


@app.route("/chef/pedido/<int:pedido_id>/aceptar", methods=["POST"])
@requiere_login("CHEF")
def chef_aceptar(pedido_id):
    try:
        OrderService().aceptar_pedido(pedido_id, usuario_actual()["id"])
        flash("Pedido aceptado. El cliente ya puede pagar.", "success")
    except OrderError as e:
        flash(str(e), "danger")
    return redirect(url_for("panel_chef"))


@app.route("/chef/pedido/<int:pedido_id>/rechazar", methods=["POST"])
@requiere_login("CHEF")
def chef_rechazar(pedido_id):
    try:
        OrderService().rechazar_pedido(pedido_id, usuario_actual()["id"], request.form.get("motivo", ""))
        flash("Pedido rechazado. Se devolvió el stock reservado.", "info")
    except OrderError as e:
        flash(str(e), "danger")
    return redirect(url_for("panel_chef"))


@app.route("/chef/pedido/<int:pedido_id>/preparar", methods=["POST"])
@requiere_login("CHEF")
def chef_preparar(pedido_id):
    try:
        OrderService().iniciar_preparacion_comando(pedido_id, usuario_actual()["id"])
        flash("Preparación iniciada.", "success")
    except OrderError as e:
        flash(str(e), "danger")
    return redirect(url_for("panel_chef"))


@app.route("/chef/pedido/<int:pedido_id>/despachar", methods=["POST"])
@requiere_login("CHEF")
def chef_despachar(pedido_id):
    try:
        resultado = OrderService().despachar_o_marcar_listo(pedido_id, usuario_actual()["id"])
        flash(resultado["mensaje"], "success")
    except OrderError as e:
        flash(str(e), "danger")
    return redirect(url_for("panel_chef"))


# ---------------------------------------------------------------------
# ENDPOINTS API JSON (Requerimiento para validación Network y AJAX)
# ---------------------------------------------------------------------
@app.route("/api/auth/perfil", methods=["GET"])
def api_perfil():
    usr = usuario_actual()
    if not usr:
        return jsonify({"autenticado": False}), 401
    return jsonify({
        "autenticado": True,
        "id": usr["id"],
        "nombre": usr["nombre"],
        "rol": usr["rol"],
        "es_chef": usr["rol"] == "CHEF"
    }), 200


@app.route("/api/pedidos/checkout", methods=["POST"])
@requiere_login("CLIENTE")
def api_checkout():
    data = request.get_json() or {}
    tipo_entrega = data.get("tipo_entrega", "DOMICILIO")
    direccion = data.get("direccion", "")
    
    carrito = session.get("carrito", [])
    if not carrito:
        return jsonify({"exito": False, "mensaje": "Tu carrito está vacío."}), 400

    try:
        RestaurantService.validar_tipo_entrega(tipo_entrega, direccion)
        carrito_items = [{"producto_id": i["producto_id"], "cantidad": i["cantidad"]} for i in carrito]
        
        pedido_id = OrderService().crear_pedido(
            cliente_id=usuario_actual()["id"],
            restaurante_id=carrito[0]["restaurante_id"],
            carrito=carrito_items,
            tipo_entrega=tipo_entrega,
            direccion_entrega=direccion if tipo_entrega == "DOMICILIO" else None,
        )
        session["carrito"] = []
        return jsonify({
            "exito": True,
            "pedido_id": pedido_id,
            "mensaje": "Pedido creado exitosamente."
        }), 201
    except (RestaurantError, OrderError) as e:
        return jsonify({"exito": False, "mensaje": str(e)}), 400


@app.route("/api/pasarela/pagar", methods=["POST"])
@requiere_login("CLIENTE")
def api_procesar_pago():
    data = request.get_json() or {}
    pedido_id = data.get("pedido_id")
    tipo_pago = data.get("tipo_pago")
    datos_tarjeta = data.get("datos_tarjeta", {})
    
    if not pedido_id or not tipo_pago:
        return jsonify({"estatus": "RECHAZADO", "mensaje": "Faltan datos de la transacción."}), 400

    try:
        # 1. Obtener el monto total del pedido
        cabecera, _ = OrderService().detalle_pedido(int(pedido_id))
        
        # 2. Procesar con el método de PaymentService
        resultado = PaymentService.procesar_pasarela(
            pedido_id=int(pedido_id), 
            tipo_pago=tipo_pago,
            datos_tarjeta=datos_tarjeta,
            monto_total=cabecera["monto_total"]
        )
        
        # 3. Validar si la pasarela rechazó la tarjeta
        if not resultado.get("exito"):
            return jsonify({"estatus": "RECHAZADO", "mensaje": resultado.get("mensaje")}), 400

        # 4. Actualizar el estado del pedido a PAGADO en la base de datos
        OrderService().marcar_como_pagado(int(pedido_id))

        # 5. Éxito
        return jsonify({
            "estatus": "APROBADO",
            "pedido_id": pedido_id,
            "detalle": {
                "transaccion_id": resultado.get("transaccion_id"),
                "mensaje": resultado.get("mensaje")
            }
        }), 200
        
    except Exception as e:
        return jsonify({"estatus": "RECHAZADO", "mensaje": str(e)}), 400


if __name__ == "__main__":
    app.run(debug=True, host="127.0.0.1", port=5000)