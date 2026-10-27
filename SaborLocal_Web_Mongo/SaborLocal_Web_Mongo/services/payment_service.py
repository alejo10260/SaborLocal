"""
services/payment_service.py
----------------------------
Cubre HU-12 (Ingresar Pago), HU-13 (Procesar Pago), HU-14 (Notificar Error
Pago) y HU-15 (Cambiar Estado a Pagado).

MongoDB: la colección 'pagos' guarda lo que ingresó el cliente y, dentro del
mismo documento, la 'confirmacion' devuelta por la pasarela (1:1 embebida).
"""

import uuid
from datetime import datetime

class PaymentError(Exception):
    """Excepción personalizada para errores en el procesamiento de pagos."""
    pass

class PaymentService:
    """Servicio para procesar pagos y validar requisitos de entrega."""

    @staticmethod
    def validar_direccion(tipo_entrega, direccion):
        if tipo_entrega == "DOMICILIO":
            if not direccion or len(direccion.strip()) < 5:
                return False, "Debe proporcionar una dirección de entrega válida (mínimo 5 caracteres)."
        return True, "Dirección válida."

    @staticmethod
    def procesar_pasarela(pedido_id, tipo_pago, datos_tarjeta, monto_total):
        num_tarjeta = datos_tarjeta.get("numero_tarjeta", "").replace(" ", "").replace("-", "")

        if len(num_tarjeta) < 13:
            return {
                "exito": False,
                "codigo": "TARJETA_INVALIDA",
                "mensaje": "Número de tarjeta no válido."
            }

        # Simulación de fallos para evaluación
        if num_tarjeta.endswith("0000"):
            return {
                "exito": False,
                "codigo": "FONDOS_INSUFFICIENTES",
                "mensaje": "Transacción rechazada por la entidad bancaria: Fondos insuficientes."
            }

        if num_tarjeta.endswith("9999"):
            return {
                "exito": False,
                "codigo": "TIMEOUT",
                "mensaje": "Tiempo de espera agotado con la pasarela de pagos."
            }

        # Pago exitoso
        return {
            "exito": True,
            "codigo": "200_OK",
            "transaccion_id": f"PAY-{uuid.uuid4().hex[:8].upper()}",
            "monto": monto_total,
            "fecha": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "mensaje": "Pago procesado exitosamente por la pasarela."
        }
        