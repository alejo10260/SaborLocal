"""
services/restaurant_service.py
-------------------------------
Cubre HU-06 (Configurar Perfil y Menú), HU-07 (Buscar y Armar Pedido) y
HU-08 (Elegir Tipo de Entrega), más la gestión del menú ya publicado
(editar perfil, agregar, editar y quitar platillos).
"""

from datetime import datetime, time as dtime

from core.database import get_db
from core.patterns import RestauranteBuilder, CatalogoIterator, resolver_estrategia_entrega


class RestaurantError(Exception):
    pass


class RestaurantService:
    def __init__(self):
        self.db = get_db()

    # ---------------- HU-06 ----------------
    def obtener_restaurante_por_usuario(self, usuario_id: int):
        return self.db.buscar_uno("restaurantes", {"usuario_id": usuario_id})

    def configurar_perfil_y_menu(self, usuario_id: int, nombre, direccion, descripcion,
                                  hora_apertura, hora_cierre, platillos: list):
        builder = RestauranteBuilder().con_datos_generales(nombre, direccion, descripcion) \
                                       .con_horario(hora_apertura, hora_cierre)
        for p in platillos:
            builder.agregar_platillo(p["nombre"], p.get("descripcion", ""), p["precio"], p["inventario"])

        errores = builder.validar()
        if errores:
            raise RestaurantError(" / ".join(errores))

        datos = builder.build()
        restaurante = self.obtener_restaurante_por_usuario(usuario_id)
        if restaurante is None:
            raise RestaurantError("No existe un restaurante asociado a este usuario.")

        ahora = datetime.now().isoformat()
        operaciones = [(
            "actualizar", "restaurantes", {"_id": restaurante["id"]},
            {"$set": {"nombre_restaurante": datos["nombre_restaurante"], "direccion": datos["direccion"],
                      "descripcion": datos["descripcion"], "hora_apertura": datos["hora_apertura"],
                      "hora_cierre": datos["hora_cierre"], "estado": "PUBLICADO"}},
        )]
        for plato in datos["platillos"]:
            operaciones.append(("insertar", "productos", {
                "restaurante_id": restaurante["id"], "nombre": plato["nombre"],
                "descripcion": plato["descripcion"], "precio": plato["precio"],
                "inventario": plato["inventario"], "esta_activo": True, "fecha_creacion": ahora,
            }))
        self.db.transaccion(operaciones)  # una sola operación atómica
        return True

    def actualizar_perfil(self, usuario_id: int, nombre, direccion, descripcion,
                           hora_apertura, hora_cierre):
        """Edita el perfil de un restaurante ya publicado (sin tocar el menú)."""
        restaurante = self.obtener_restaurante_por_usuario(usuario_id)
        if restaurante is None:
            raise RestaurantError("No existe un restaurante asociado a este usuario.")
        if not (nombre or "").strip() or not (direccion or "").strip():
            raise RestaurantError("El nombre y la dirección del restaurante son obligatorios.")
        if not hora_apertura or not hora_cierre:
            raise RestaurantError("Debes definir el horario de atención.")
        self.db.actualizar("restaurantes", {"_id": restaurante["id"]}, {"$set": {
            "nombre_restaurante": nombre.strip(), "direccion": direccion.strip(),
            "descripcion": descripcion, "hora_apertura": hora_apertura, "hora_cierre": hora_cierre,
        }})
        self.db.log_evento(None, usuario_id, "RESTAURANTE_EDITADO", f"Restaurante id={restaurante['id']}")
        return True

    # ---------------- HU-07 ----------------
    def listar_restaurantes_publicados(self):
        """Solo restaurantes 'Publicado'; indica si están en horario de atención."""
        ahora = datetime.now().time()
        resultado = []
        for r in self.db.buscar("restaurantes", {"estado": "PUBLICADO"}):
            en_horario = True
            if r.get("hora_apertura") and r.get("hora_cierre"):
                try:
                    apertura = dtime.fromisoformat(r["hora_apertura"])
                    cierre = dtime.fromisoformat(r["hora_cierre"])
                    en_horario = apertura <= ahora <= cierre
                except ValueError:
                    en_horario = True
            resultado.append(r | {"en_horario": en_horario})
        return resultado

    def listar_productos(self, restaurante_id: int):
        productos = self.db.buscar("productos", {"restaurante_id": restaurante_id, "esta_activo": True})
        # Uso explícito del Patrón Iterator para recorrer el catálogo (HU-07)
        return list(CatalogoIterator(productos))

    def obtener_producto(self, producto_id: int):
        """Lectura en tiempo real del producto (sin caché), para validar stock."""
        return self.db.buscar_uno("productos", {"_id": producto_id, "esta_activo": True})

    # ---------------- Gestión del menú ya publicado ----------------
    def obtener_producto_de_chef(self, producto_id: int, usuario_id: int):
        """Trae el producto SOLO si pertenece al restaurante del chef autenticado.
        Usa $lookup productos -> restaurantes (equivale al JOIN relacional)."""
        filas = self.db.agregar("productos", [
            {"$match": {"_id": producto_id, "esta_activo": True}},
            {"$lookup": {"from": "restaurantes", "localField": "restaurante_id",
                         "foreignField": "_id", "as": "restaurante"}},
            {"$unwind": "$restaurante"},
            {"$match": {"restaurante.usuario_id": usuario_id}},
        ])
        if not filas:
            raise RestaurantError("Producto no encontrado o no pertenece a tu restaurante.")
        producto = filas[0]
        producto.pop("restaurante", None)
        return producto

    @staticmethod
    def _validar_platillo(nombre, precio, inventario):
        if not nombre or not nombre.strip():
            raise RestaurantError("El nombre del platillo es obligatorio.")
        if precio is None or precio <= 0:
            raise RestaurantError("El precio debe ser mayor a $0.")
        if inventario is None or inventario < 0:
            raise RestaurantError("El inventario (stock) no puede ser negativo.")

    def agregar_platillo(self, usuario_id: int, nombre: str, descripcion: str,
                          precio: float, inventario: int):
        """Agrega un platillo directamente al menú de un restaurante ya publicado."""
        self._validar_platillo(nombre, precio, inventario)
        restaurante = self.obtener_restaurante_por_usuario(usuario_id)
        if restaurante is None:
            raise RestaurantError("No existe un restaurante asociado a este usuario.")
        pid = self.db.insertar("productos", {
            "restaurante_id": restaurante["id"], "nombre": nombre.strip(), "descripcion": descripcion,
            "precio": precio, "inventario": inventario, "esta_activo": True,
            "fecha_creacion": datetime.now().isoformat(),
        })
        self.db.log_evento(None, usuario_id, "PRODUCTO_AGREGADO", f"Producto id={pid} ('{nombre.strip()}')")
        return pid

    def actualizar_producto(self, producto_id: int, usuario_id: int, nombre: str,
                             descripcion: str, precio: float, inventario: int):
        self._validar_platillo(nombre, precio, inventario)
        producto = self.obtener_producto_de_chef(producto_id, usuario_id)
        self.db.actualizar("productos", {"_id": producto["id"]}, {"$set": {
            "nombre": nombre.strip(), "descripcion": descripcion,
            "precio": precio, "inventario": inventario,
        }})
        self.db.log_evento(None, usuario_id, "PRODUCTO_EDITADO",
                            f"Producto id={producto['id']} ('{nombre.strip()}') actualizado.")
        return True

    def quitar_producto(self, producto_id: int, usuario_id: int):
        """Lo retira del catálogo (esta_activo=False); se conserva en pedidos antiguos."""
        producto = self.obtener_producto_de_chef(producto_id, usuario_id)
        self.db.actualizar("productos", {"_id": producto["id"]}, {"$set": {"esta_activo": False}})
        self.db.log_evento(None, usuario_id, "PRODUCTO_QUITADO", f"Producto id={producto['id']}")
        return True

    @staticmethod
    def calcular_subtotal(carrito_con_precios: list) -> float:
        return round(sum(item["precio"] * item["cantidad"] for item in carrito_con_precios), 2)

    # ---------------- HU-08 ----------------
    @staticmethod
    def validar_tipo_entrega(tipo_entrega: str, direccion_entrega: str):
        estrategia = resolver_estrategia_entrega(tipo_entrega)
        if estrategia.requiere_direccion() and not (direccion_entrega or "").strip():
            raise RestaurantError("Debe ingresar la dirección de entrega para la modalidad Domicilio.")
        return True
