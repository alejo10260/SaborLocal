"""
services/order_service.py
--------------------------
Cubre HU-09 (Validar Stock), HU-10 (Notificar Falta Stock),
HU-11 (Notificar Pedido al Chef), HU-15 (Cambiar Estado a Pagado),
HU-16 (Preparar Pedido), HU-17 (Despachar/Recoger), HU-18 (Notificar
Avance) y HU-19 (Confirmar Recepción).

MongoDB: los ítems del pedido (relación muchos a muchos pedidos <-> productos)
se guardan como arreglo 'items' dentro del pedido y se resuelven con $lookup.
"""

from datetime import datetime

from core.database import get_db
from core.patterns import (
    OrderValidatorFacade, get_canal_eventos, PedidoEstadoMachine,
    TransicionInvalidaError, ComandoIniciarPreparacion, resolver_estrategia_entrega,
)


class OrderError(Exception):
    pass


COMISION_PORCENTAJE = 0.10  # 10% de comisión de la plataforma


class OrderService:
    def __init__(self):
        self.db = get_db()
        self.canal = get_canal_eventos()

    # ---------------- HU-09: Validar Stock (Facade) ----------------
    def validar_carrito(self, carrito: list, restaurante_id: int):
        facade = OrderValidatorFacade(self.db)
        return facade.validate(carrito, restaurante_id)

    # ---------------- HU-09/10/11: crear pedido tras validar ----------------
    def crear_pedido(self, cliente_id: int, restaurante_id: int, carrito: list,
                       tipo_entrega: str, direccion_entrega: str = None):
        es_valido, fallidos = self.validar_carrito(carrito, restaurante_id)
        if not es_valido:
            # HU-10: notificar qué productos fallaron, sin crear el pedido
            raise OrderError("Stock insuficiente: " + "; ".join(
                f.get('error') or f"{f.get('nombre','?')} (disponible {f.get('disponible','?')}, "
                                  f"solicitado {f.get('solicitado','?')})" for f in fallidos
            ))

        # Descuento de stock ATÓMICO por producto: si dos clientes compran la
        # última unidad al mismo tiempo, solo uno logra descontarla.
        descontados, items, subtotal = [], [], 0.0
        for item in carrito:
            producto = self.db.buscar_uno("productos", {"_id": item["producto_id"]})
            if not self.db.descontar_stock(item["producto_id"], item["cantidad"]):
                for pid, cant in descontados:           # deshace lo ya descontado
                    self.db.devolver_stock(pid, cant)
                raise OrderError(
                    f"Stock insuficiente: {producto['nombre']} se agotó mientras confirmabas tu pedido."
                )
            descontados.append((item["producto_id"], item["cantidad"]))
            sub = round(producto["precio"] * item["cantidad"], 2)
            subtotal += sub
            items.append({"producto_id": producto["id"], "precio_unitario": producto["precio"],
                          "cantidad": item["cantidad"], "subtotal": sub})

        subtotal = round(subtotal, 2)
        comision = round(subtotal * COMISION_PORCENTAJE, 2)
        total = round(subtotal + comision, 2)
        ahora = datetime.now().isoformat()
        try:
            pedido_id = self.db.insertar("pedidos", {
                "cliente_id": cliente_id, "restaurante_id": restaurante_id,
                "tipo_entrega": tipo_entrega, "direccion_entrega": direccion_entrega,
                "subtotal": subtotal, "monto_comision": comision, "monto_total": total,
                "estado": "PENDIENTE_CHEF", "items": items,   # <- relación N:M embebida
                "fecha_creacion": ahora, "fecha_actualizacion": ahora,
            })
        except Exception:
            for pid, cant in descontados:
                self.db.devolver_stock(pid, cant)
            raise
        self.db.log_evento(pedido_id, cliente_id, "PEDIDO_CREADO", f"Total: {total}")

        # HU-11: notificación push (Observer/Pub-Sub) al panel del chef
        self.canal.publicar("NUEVO_PEDIDO_CHEF", {
            "restaurante_id": restaurante_id, "pedido_id": pedido_id, "monto_total": total,
        })
        return pedido_id

    # ---------------- Aceptar / Rechazar pedido por el Chef ----------------
    def aceptar_pedido(self, pedido_id: int, chef_id: int):
        """El chef decide si puede preparar el pedido. No cambia el estado
        (sigue 'PENDIENTE_CHEF'), pero deja constancia y habilita el pago."""
        pedido = self.db.buscar_uno("pedidos", {"_id": pedido_id})
        if pedido is None:
            raise OrderError("Pedido no encontrado.")
        if pedido["estado"] != "PENDIENTE_CHEF":
            raise OrderError("Solo se pueden aceptar pedidos en estado 'Esperando confirmación del Chef'.")
        self.db.log_evento(pedido_id, chef_id, "PEDIDO_ACEPTADO_CHEF", "")
        self.canal.publicar("PEDIDO_ACEPTADO_CLIENTE", {"pedido_id": pedido_id})
        return {"ok": True}

    def rechazar_pedido(self, pedido_id: int, chef_id: int, motivo: str = ""):
        pedido = self.db.buscar_uno("pedidos", {"_id": pedido_id})
        if pedido is None:
            raise OrderError("Pedido no encontrado.")
        nuevo_estado = PedidoEstadoMachine.transicionar(pedido["estado"], "RECHAZADO")
        for it in pedido.get("items", []):                 # devuelve el stock reservado
            self.db.devolver_stock(it["producto_id"], it["cantidad"])
        self._actualizar_estado(pedido_id, nuevo_estado)
        self.db.log_evento(pedido_id, chef_id, "PEDIDO_RECHAZADO_CHEF", motivo)
        self.canal.publicar("ACTUALIZACION_PEDIDO_CLIENTE", {"pedido_id": pedido_id, "estado": nuevo_estado})
        return {"ok": True}

    def pedido_fue_aceptado(self, pedido_id: int) -> bool:
        return self.db.buscar_uno(
            "historial_estados", {"pedido_id": pedido_id, "evento": "PEDIDO_ACEPTADO_CHEF"}
        ) is not None

    # ---------------- HU-15: Cambiar Estado a Pagado (¡NUEVO!) ----------------
    def marcar_como_pagado(self, pedido_id: int):
        """Actualiza el pedido a PAGADO de forma segura tras la aprobación de pasarela."""
        pedido = self.db.buscar_uno("pedidos", {"_id": pedido_id})
        if pedido is None:
            raise OrderError("Pedido no encontrado.")
        
        # Transiciona el estado verificando reglas de negocio
        try:
            nuevo_estado = PedidoEstadoMachine.transicionar(pedido["estado"], "PAGADO")
        except Exception as e:
            raise OrderError(f"No se pudo registrar el pago: {str(e)}")

        self._actualizar_estado(pedido_id, nuevo_estado)
        self.db.log_evento(pedido_id, pedido["cliente_id"], "PAGO_CONFIRMADO", "Pago aprobado por pasarela")
        self.canal.publicar("ACTUALIZACION_PEDIDO_CLIENTE", {"pedido_id": pedido_id, "estado": nuevo_estado})
        return {"ok": True, "estado": nuevo_estado}

    # ---------------- HU-16: Preparar Pedido ----------------
    def iniciar_preparacion_comando(self, pedido_id: int, chef_id: int):
        """Punto de entrada que usa el Patrón Command (idempotente ante doble clic)."""
        comando = ComandoIniciarPreparacion(self, pedido_id, chef_id)
        return comando.ejecutar()

    def iniciar_preparacion(self, pedido_id: int, chef_id: int):
        pedido = self.db.buscar_uno("pedidos", {"_id": pedido_id})
        if pedido is None:
            raise OrderError("Pedido no encontrado.")
        if pedido["estado"] == "EN_PREPARACION":
            return {"ok": True, "estado": "EN_PREPARACION", "info": "Ya estaba en preparación."}
        if pedido["estado"] != "PAGADO":
            raise OrderError("Solo se puede iniciar preparación de pedidos en estado 'PAGADO'.")

        nuevo_estado = PedidoEstadoMachine.transicionar(pedido["estado"], "EN_PREPARACION")
        self._actualizar_estado(pedido_id, nuevo_estado)
        self.db.log_evento(pedido_id, chef_id, "PREPARACION_INICIADA", "")
        self.canal.publicar("ACTUALIZACION_PEDIDO_CLIENTE", {"pedido_id": pedido_id, "estado": nuevo_estado})
        return {"ok": True, "estado": nuevo_estado}

    # ---------------- HU-17: Despachar / Recoger ----------------
    def despachar_o_marcar_listo(self, pedido_id: int, chef_id: int):
        pedido = self.db.buscar_uno("pedidos", {"_id": pedido_id})
        if pedido is None:
            raise OrderError("Pedido no encontrado.")
        if pedido["estado"] != "EN_PREPARACION":
            raise OrderError("El pedido debe estar 'En preparación' para despachar/marcar listo.")

        estrategia = resolver_estrategia_entrega(pedido["tipo_entrega"])
        nuevo_estado = "EN_TRANSITO" if pedido["tipo_entrega"] == "DOMICILIO" else "LISTO_PARA_RECOGER"
        nuevo_estado = PedidoEstadoMachine.transicionar(pedido["estado"], nuevo_estado)
        self._actualizar_estado(pedido_id, nuevo_estado)
        self.db.log_evento(pedido_id, chef_id, "DESPACHO_EJECUTADO", estrategia.accion_despacho())

        # ---------------- HU-18: Notificar Avance ----------------
        mensaje = (f"En camino a {pedido['direccion_entrega']}" if nuevo_estado == "EN_TRANSITO"
                   else "Listo para retiro en el local")
        self.canal.publicar("ACTUALIZACION_PEDIDO_CLIENTE", {
            "pedido_id": pedido_id, "estado": nuevo_estado, "mensaje": mensaje,
        })
        return {"ok": True, "estado": nuevo_estado, "mensaje": mensaje}

    # ---------------- HU-19: Confirmar Recepción ----------------
    def confirmar_recepcion(self, pedido_id: int, cliente_id: int):
        pedido = self.db.buscar_uno("pedidos", {"_id": pedido_id})
        if pedido is None:
            raise OrderError("Pedido no encontrado.")
        if pedido["cliente_id"] != cliente_id:
            raise OrderError("No autorizado: este pedido no pertenece al usuario autenticado.")
        if pedido["estado"] not in ("EN_TRANSITO", "LISTO_PARA_RECOGER"):
            raise OrderError("El pedido no está en un estado válido para confirmar recepción.")

        nuevo_estado = PedidoEstadoMachine.transicionar(pedido["estado"], "COMPLETADO")
        self._actualizar_estado(pedido_id, nuevo_estado)
        self.db.log_evento(pedido_id, cliente_id, "RECEPCION_CONFIRMADA", "")
        self.canal.publicar("PEDIDO_COMPLETADO", {"pedido_id": pedido_id})
        return {"ok": True, "estado": nuevo_estado}

    # ---------------- utilidades ----------------
    def _actualizar_estado(self, pedido_id: int, nuevo_estado: str):
        self.db.actualizar("pedidos", {"_id": pedido_id}, {"$set": {
            "estado": nuevo_estado, "fecha_actualizacion": datetime.now().isoformat()}})

    def listar_pedidos_de_chef(self, restaurante_id: int, estados=None):
        filtro = {"restaurante_id": restaurante_id}
        if estados:
            filtro["estado"] = {"$in": list(estados)}
        return self.db.buscar("pedidos", filtro, orden=[("fecha_creacion", -1)])

    def listar_pedidos_de_cliente(self, cliente_id: int):
        """$lookup pedidos -> restaurantes para traer el nombre del restaurante."""
        return self.db.agregar("pedidos", [
            {"$match": {"cliente_id": cliente_id}},
            {"$lookup": {"from": "restaurantes", "localField": "restaurante_id",
                         "foreignField": "_id", "as": "restaurante"}},
            {"$unwind": "$restaurante"},
            {"$addFields": {"nombre_restaurante": "$restaurante.nombre_restaurante"}},
            {"$project": {"restaurante": 0}},
            {"$sort": {"fecha_creacion": -1}},
        ])

    def detalle_pedido(self, pedido_id: int):
        """Resuelve la relación MUCHOS A MUCHOS pedidos <-> productos con $lookup
        sobre el arreglo 'items' (reemplaza al JOIN con 'detalles_pedido')."""
        cabecera = self.db.buscar_uno("pedidos", {"_id": pedido_id})
        detalles = self.db.agregar("pedidos", [
            {"$match": {"_id": pedido_id}},
            {"$unwind": "$items"},
            {"$lookup": {"from": "productos", "localField": "items.producto_id",
                         "foreignField": "_id", "as": "producto"}},
            {"$unwind": "$producto"},
            {"$project": {"_id": 0, "producto_id": "$items.producto_id", "nombre": "$producto.nombre",
                          "cantidad": "$items.cantidad", "precio_unitario": "$items.precio_unitario",
                          "subtotal": "$items.subtotal"}},
        ])
        return cabecera, detalles