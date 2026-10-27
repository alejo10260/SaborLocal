# SaborLocal — versión Web (Flask + MongoDB)

Roles: **Cliente** y **Chef** (se eliminó el rol administrador).
El chef queda activo al registrarse: inicia sesión, configura su perfil y
sus platillos, publica el restaurante y puede editarlo todo después.

## Instalación
```
pip install -r requirements.txt
```

## Ejecutar con MongoDB real
1. Instala y arranca MongoDB (o usa un cluster de MongoDB Atlas).
2. (Opcional) define la conexión:
   - `MONGO_URI`  (por defecto `mongodb://localhost:27017`)
   - `MONGO_DB`   (por defecto `saborlocal`)
3. `python app.py` y abre http://127.0.0.1:5000

## Ejecutar sin instalar MongoDB (demo)
Usa una base MongoDB en memoria (mongomock); los datos se pierden al cerrar:
```
# Linux / Mac
SABORLOCAL_MOCK=1 python app.py
# Windows (PowerShell)
$env:SABORLOCAL_MOCK="1"; python app.py
```

## Colecciones de MongoDB
usuarios, restaurantes, productos, pedidos, pagos, calificaciones, recibos,
historial_estados y contadores (ids numéricos autoincrementales).

- La relación muchos a muchos pedidos <-> productos es el arreglo
  `pedidos.items` (referencia a `productos._id`) y se resuelve con `$lookup`.
- `pagos.confirmacion` es un subdocumento embebido (1:1).
- Índices únicos: `usuarios.correo_electronico`, `restaurantes.usuario_id`,
  `calificaciones.pedido_id`, `recibos.pedido_id`.
- El stock se descuenta con una actualización atómica condicional
  (`$inc` con filtro `inventario >= cantidad`).
- Transacciones: con replica set se usa una transacción real de MongoDB;
  con un servidor standalone se aplica compensación (se deshace lo hecho si
  algo falla).

## Flujo de prueba
1. Regístrate como Chef, inicia sesión, agrega platillos y publica.
2. Regístrate como Cliente, agrega productos al carrito (no puedes pasar el
   stock disponible) y confirma el pedido.
3. Como Chef acepta el pedido; como Cliente paga (tarjeta de prueba
   `4111111111111111`; terminada en `0000` = fondos insuficientes, `9999` = timeout).
4. Chef: iniciar preparación y despachar / marcar listo.
5. Cliente: confirmar recepción y calificar.
