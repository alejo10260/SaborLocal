"""
core/database.py
----------------
Capa de datos de SaborLocal con MongoDB (NoSQL, driver pymongo).

Decisiones de diseño (reemplazan al esquema relacional de SQLite):
  * Colecciones: usuarios, restaurantes, productos, pedidos, pagos,
    calificaciones, recibos, historial_estados y contadores.
  * La relación MUCHOS A MUCHOS pedidos <-> productos (antes la tabla
    'detalles_pedido') ahora vive como un arreglo 'items' DENTRO del pedido
    que referencia a 'productos._id'; se resuelve con $lookup.
  * La confirmación del pago se guarda como subdocumento 'confirmacion'
    dentro de 'pagos' (relación 1:1 embebida).
  * Los ids siguen siendo numéricos (colección 'contadores') para que las
    URLs y plantillas no cambien.
  * El stock se descuenta con una actualización atómica condicional
    ($inc con filtro inventario >= cantidad), que evita la condición de
    carrera de dos clientes comprando la última unidad (HU-09).

Conexión:
  MONGO_URI  (por defecto mongodb://localhost:27017)
  MONGO_DB   (por defecto saborlocal)
  SABORLOCAL_MOCK=1 usa 'mongomock' (MongoDB en memoria) para demos/pruebas
  sin necesidad de instalar un servidor.
"""

import os
import threading
from datetime import datetime

from pymongo import MongoClient, ASCENDING, ReturnDocument
from pymongo.errors import DuplicateKeyError, ServerSelectionTimeoutError  # noqa: F401

MONGO_URI = os.environ.get("MONGO_URI", "mongodb://localhost:27017")
MONGO_DB = os.environ.get("MONGO_DB", "saborlocal")
USAR_MOCK = os.environ.get("SABORLOCAL_MOCK") == "1"


def _normalizar(doc):
    """Agrega la clave 'id' (copia de _id) para que servicios y plantillas
    puedan usar r.id / p['id'] igual que antes."""
    if doc is None:
        return None
    d = dict(doc)
    if "_id" in d:
        d["id"] = d["_id"]
    return d


class Database:
    """Singleton: una única conexión MongoDB compartida por toda la app."""
    _instance = None
    _lock = threading.Lock()

    def __new__(cls, *args, **kwargs):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._inicializado = False
            return cls._instance

    def __init__(self):
        if self._inicializado:
            return
        self._lock_db = threading.RLock()
        self.soporta_transacciones = False

        if USAR_MOCK:
            import mongomock
            self.client = mongomock.MongoClient()
        else:
            self.client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=3000)
            try:
                info = self.client.admin.command("hello")
            except ServerSelectionTimeoutError as e:
                raise RuntimeError(
                    "No se pudo conectar a MongoDB en " + MONGO_URI + ". Inicia el servidor "
                    "(mongod) o define MONGO_URI; para una demo sin servidor usa SABORLOCAL_MOCK=1."
                ) from e
            # Las transacciones multi-documento exigen replica set o mongos
            self.soporta_transacciones = bool(info.get("setName") or info.get("msg") == "isdbgrid")

        self.db = self.client[MONGO_DB]
        self._crear_indices()
        self._inicializado = True

    # ------------------------------------------------------------------
    # Índices (equivalen a las restricciones UNIQUE / FK del modelo relacional)
    # ------------------------------------------------------------------
    def _crear_indices(self):
        self.db.usuarios.create_index([("correo_electronico", ASCENDING)], unique=True)
        self.db.restaurantes.create_index([("usuario_id", ASCENDING)], unique=True)
        self.db.productos.create_index([("restaurante_id", ASCENDING)])
        self.db.pedidos.create_index([("cliente_id", ASCENDING)])
        self.db.pedidos.create_index([("restaurante_id", ASCENDING)])
        self.db.pagos.create_index([("pedido_id", ASCENDING)])
        self.db.calificaciones.create_index([("pedido_id", ASCENDING)], unique=True)  # 1 reseña por pedido
        self.db.recibos.create_index([("pedido_id", ASCENDING)], unique=True)
        self.db.historial_estados.create_index([("pedido_id", ASCENDING)])

    # ------------------------------------------------------------------
    # Ids numéricos autoincrementales
    # ------------------------------------------------------------------
    def siguiente_id(self, coleccion: str) -> int:
        doc = self.db.contadores.find_one_and_update(
            {"_id": coleccion}, {"$inc": {"seq": 1}}, upsert=True,
            return_document=ReturnDocument.AFTER,
        )
        return doc["seq"]

    # ------------------------------------------------------------------
    # Operaciones básicas
    # ------------------------------------------------------------------
    def insertar(self, coleccion: str, doc: dict, sesion=None) -> int:
        doc = dict(doc)
        if "_id" not in doc:
            doc["_id"] = self.siguiente_id(coleccion)
        with self._lock_db:
            self.db[coleccion].insert_one(doc, session=sesion) if sesion else self.db[coleccion].insert_one(doc)
        return doc["_id"]

    def buscar(self, coleccion: str, filtro: dict = None, orden: list = None):
        with self._lock_db:
            cur = self.db[coleccion].find(filtro or {})
            if orden:
                cur = cur.sort(orden)
            return [_normalizar(d) for d in cur]

    def buscar_uno(self, coleccion: str, filtro: dict):
        with self._lock_db:
            return _normalizar(self.db[coleccion].find_one(filtro))

    def actualizar(self, coleccion: str, filtro: dict, cambios: dict, sesion=None) -> int:
        with self._lock_db:
            if sesion:
                r = self.db[coleccion].update_many(filtro, cambios, session=sesion)
            else:
                r = self.db[coleccion].update_many(filtro, cambios)
            return r.modified_count

    def agregar(self, coleccion: str, pipeline: list):
        """Pipeline de agregación ($match, $lookup, $unwind, $group, ...)."""
        with self._lock_db:
            return [_normalizar(d) for d in self.db[coleccion].aggregate(pipeline)]

    # ------------------------------------------------------------------
    # Stock atómico (HU-09): descuenta SOLO si alcanza el inventario
    # ------------------------------------------------------------------
    def descontar_stock(self, producto_id: int, cantidad: int) -> bool:
        with self._lock_db:
            r = self.db.productos.update_one(
                {"_id": producto_id, "esta_activo": True, "inventario": {"$gte": cantidad}},
                {"$inc": {"inventario": -cantidad}},
            )
            return r.modified_count == 1

    def devolver_stock(self, producto_id: int, cantidad: int):
        with self._lock_db:
            self.db.productos.update_one({"_id": producto_id}, {"$inc": {"inventario": cantidad}})

    # ------------------------------------------------------------------
    # Operación atómica de varios pasos (HU-15)
    #   operaciones: ("insertar", col, doc) | ("actualizar", col, filtro, cambios)
    # Con replica set usa una transacción real de MongoDB; en un servidor
    # standalone aplica compensación (deshace lo ya hecho si algo falla).
    # ------------------------------------------------------------------
    def transaccion(self, operaciones: list):
        if self.soporta_transacciones:
            with self.client.start_session() as sesion:
                return sesion.with_transaction(lambda s: self._aplicar(operaciones, s)[0])
        ids, deshacer = [], []
        try:
            ids, deshacer = self._aplicar(operaciones, None, deshacer)
        except Exception:
            for fn in reversed(deshacer):
                fn()
            raise
        return ids

    def _aplicar(self, operaciones, sesion, deshacer=None):
        deshacer = deshacer if deshacer is not None else []
        ids = []
        for op in operaciones:
            if op[0] == "insertar":
                _, col, doc = op
                nuevo_id = self.insertar(col, doc, sesion)
                ids.append(nuevo_id)
                deshacer.append(lambda c=col, i=nuevo_id: self.db[c].delete_one({"_id": i}))
            elif op[0] == "actualizar":
                _, col, filtro, cambios = op
                antes = list(self.db[col].find(filtro))
                self.actualizar(col, filtro, cambios, sesion)
                for d in antes:
                    deshacer.append(lambda c=col, dd=d: self.db[c].replace_one({"_id": dd["_id"]}, dd))
        return ids, deshacer

    # ------------------------------------------------------------------
    # Auditoría (HU-03 / HU-16): log de eventos
    # ------------------------------------------------------------------
    def log_evento(self, pedido_id, actor_id, evento, detalle=""):
        self.insertar("historial_estados", {
            "pedido_id": pedido_id, "actor_id": actor_id, "evento": evento,
            "detalle": detalle, "fecha": datetime.now().isoformat(),
        })


def get_db() -> Database:
    return Database()
