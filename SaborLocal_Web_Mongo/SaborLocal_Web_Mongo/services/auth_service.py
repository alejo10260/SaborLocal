"""
services/auth_service.py
-------------------------
Cubre HU-01 (Registrar Cliente), HU-02 (Iniciar Sesión), HU-03 (Validar
Credenciales) y HU-04 (Registrar Chef).

Sin rol administrador: el chef queda ACTIVO al registrarse y puede iniciar
sesión de inmediato para configurar su restaurante (la antigua HU-05 de
aprobación se eliminó).
"""

from datetime import datetime

from core.database import get_db
from core.security import hash_password, verify_password, generar_token
from core.dtos import UserRegistrationDTO, ChefRegistrationDTO
from core.patterns import UsuarioFactory, resolver_estrategia_redireccion


class AuthError(Exception):
    pass


class AuthService:
    def __init__(self):
        self.db = get_db()

    # ---------------- HU-01: Registrar Cliente ----------------
    def registrar_cliente(self, dto: UserRegistrationDTO):
        errores = dto.validar()
        if errores:
            raise AuthError(" / ".join(errores))

        if self.db.buscar_uno("usuarios", {"correo_electronico": dto.correo_electronico}):
            raise AuthError("El correo electrónico ya se encuentra registrado.")

        datos = UsuarioFactory.crear_cliente(dto.nombre.strip(), dto.correo_electronico,
                                             hash_password(dto.contrasena))
        datos["fecha_creacion"] = datetime.now().isoformat()
        self.db.insertar("usuarios", datos)
        return True  # el frontend redirige manualmente al login (HU-01)

    # ---------------- HU-04: Registrar Chef ----------------
    def registrar_chef(self, dto: ChefRegistrationDTO):
        errores = dto.validar()
        if errores:
            raise AuthError(" / ".join(errores))

        if self.db.buscar_uno("usuarios", {"correo_electronico": dto.correo_electronico}):
            raise AuthError("El correo electrónico ya se encuentra registrado.")

        datos_usuario = UsuarioFactory.crear_chef(dto.nombre.strip(), dto.correo_electronico,
                                                  hash_password(dto.contrasena))
        ahora = datetime.now().isoformat()
        datos_usuario["fecha_creacion"] = ahora
        usuario_id = self.db.siguiente_id("usuarios")
        restaurante_id = self.db.siguiente_id("restaurantes")
        # Usuario + restaurante en BORRADOR se guardan juntos (operación atómica)
        self.db.transaccion([
            ("insertar", "usuarios", {"_id": usuario_id, **datos_usuario}),
            ("insertar", "restaurantes", {
                "_id": restaurante_id, "usuario_id": usuario_id,
                "nombre_restaurante": dto.nombre_restaurante, "direccion": dto.direccion,
                "descripcion": dto.descripcion, "estado": "BORRADOR",
                "hora_apertura": None, "hora_cierre": None, "fecha_creacion": ahora,
            }),
        ])
        self.db.log_evento(None, usuario_id, "CHEF_REGISTRADO",
                            f"Restaurante '{dto.nombre_restaurante}' creado en borrador.")
        return True

    # ---------------- HU-02 / HU-03: Iniciar sesión + validar credenciales ----------------
    def iniciar_sesion(self, correo: str, contrasena: str):
        if not correo or not contrasena:
            raise AuthError("Correo y contraseña son obligatorios.")

        usuario = self.db.buscar_uno("usuarios", {"correo_electronico": correo})
        if usuario is None or not verify_password(contrasena, usuario["contrasena_hash"]):
            self.db.log_evento(None, None, "LOGIN_FALLIDO", f"Intento fallido para correo {correo}.")
            # Mensaje genérico: no revela si falló correo o contraseña (HU-03)
            raise AuthError("Credenciales inválidas.")

        if not usuario["esta_activo"]:
            raise AuthError("La cuenta está desactivada.")

        estrategia = resolver_estrategia_redireccion(usuario["rol"])
        payload = {"id": usuario["id"], "nombre": usuario["nombre"] or "",
                   "correo": usuario["correo_electronico"], "rol": usuario["rol"]}
        token = generar_token(payload)
        self.db.log_evento(None, usuario["id"], "LOGIN_EXITOSO", "")
        return {
            "usuario": payload,
            "token": token,
            "pantalla_destino": estrategia.pantalla_destino(),
        }
