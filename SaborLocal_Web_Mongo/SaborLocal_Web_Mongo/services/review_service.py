"""
services/review_service.py
----------------------------
Cubre HU-20 (Evaluar Vendedor). Sin rol administrador, el módulo de
disputas/reclamos (que lo resolvía el administrador) se eliminó.
"""

from datetime import datetime

from pymongo.errors import DuplicateKeyError

from core.database import get_db
from core.patterns import Sujeto


class ReviewError(Exception):
    pass


class ReviewService:
    def __init__(self):
        self.db = get_db()
        # HU-20 - Patrón Observer: al persistir la calificación se dispara un
        # evento para recalcular el promedio del chef.
        self._sujeto = Sujeto()
        self._sujeto.suscribir(self._recalcular_promedio)

    def pedido_calificado(self, pedido_id: int) -> bool:
        return self.db.buscar_uno("calificaciones", {"pedido_id": pedido_id}) is not None

    def calificar_pedido(self, pedido_id: int, cliente_id: int, puntuacion: int, comentario: str = ""):
        pedido = self.db.buscar_uno("pedidos", {"_id": pedido_id})
        if pedido is None:
            raise ReviewError("Pedido no encontrado.")
        if pedido["cliente_id"] != cliente_id:
            raise ReviewError("No autorizado para calificar este pedido.")
        if pedido["estado"] != "COMPLETADO":
            raise ReviewError("Solo se pueden calificar pedidos en estado 'Completado'.")
        if not (1 <= puntuacion <= 5):
            raise ReviewError("La puntuación debe estar entre 1 y 5 estrellas.")
        if not pedido.get("items"):
            raise ReviewError("El pedido no tiene detalle registrado; no se puede calificar.")
        if self.pedido_calificado(pedido_id):
            raise ReviewError("Este pedido ya fue calificado (restricción única).")

        # Solo se guarda pedido_id: cliente y restaurante se derivan siempre por $lookup.
        try:
            self.db.insertar("calificaciones", {
                "pedido_id": pedido_id, "puntuacion": puntuacion, "comentario": comentario,
                "fecha_creacion": datetime.now().isoformat(),
            })
        except DuplicateKeyError:   # índice UNIQUE sobre pedido_id
            raise ReviewError("Este pedido ya fue calificado (restricción única).")
        self._sujeto.notificar("NUEVA_CALIFICACION", {"restaurante_id": pedido["restaurante_id"]})
        return True

    def _recalcular_promedio(self, evento, datos):
        return self.promedio_restaurante(datos["restaurante_id"])

    def promedio_restaurante(self, restaurante_id: int):
        """$lookup calificaciones -> pedidos para derivar el restaurante, y $group para promediar."""
        filas = self.db.agregar("calificaciones", [
            {"$lookup": {"from": "pedidos", "localField": "pedido_id",
                         "foreignField": "_id", "as": "pedido"}},
            {"$unwind": "$pedido"},
            {"$match": {"pedido.restaurante_id": restaurante_id}},
            {"$group": {"_id": None, "promedio": {"$avg": "$puntuacion"}, "total": {"$sum": 1}}},
        ])
        if not filas:
            return None, 0
        return round(filas[0]["promedio"], 2), filas[0]["total"]

    def listar_calificaciones_restaurante(self, restaurante_id: int):
        return self.db.agregar("calificaciones", [
            {"$lookup": {"from": "pedidos", "localField": "pedido_id",
                         "foreignField": "_id", "as": "pedido"}},
            {"$unwind": "$pedido"},
            {"$match": {"pedido.restaurante_id": restaurante_id}},
            {"$lookup": {"from": "usuarios", "localField": "pedido.cliente_id",
                         "foreignField": "_id", "as": "cliente"}},
            {"$unwind": "$cliente"},
            {"$addFields": {"cliente_correo": "$cliente.correo_electronico"}},
            {"$project": {"pedido": 0, "cliente": 0}},
            {"$sort": {"fecha_creacion": -1}},
        ])
