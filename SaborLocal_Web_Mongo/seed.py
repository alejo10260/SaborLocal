from pymongo import MongoClient

client = MongoClient('mongodb://localhost:27017/')
db = client['saborlocal']

# Reiniciar base de datos para evitar duplicados
client.drop_database('saborlocal')

# 1. USUARIOS (Clientes, Chefs y Administradores)
db.usuarios.insert_many([
    {'_id': 10, 'nombre': 'Maria Lopez', 'correo_electronico': 'maria@gmail.com', 'contrasena_hash': 'hash_10', 'rol': 'CLIENTE', 'esta_activo': True, 'fecha_creacion': '2026-10-22T10:00:00'},
    {'_id': 11, 'nombre': 'Juan Perez', 'correo_electronico': 'juan@gmail.com', 'contrasena_hash': 'hash_11', 'rol': 'CLIENTE', 'esta_activo': True, 'fecha_creacion': '2026-10-22T10:15:00'},
    {'_id': 12, 'nombre': 'Laura Gomez', 'correo_electronico': 'laura@gmail.com', 'contrasena_hash': 'hash_12', 'rol': 'CLIENTE', 'esta_activo': True, 'fecha_creacion': '2026-10-22T10:30:00'},
    {'_id': 13, 'nombre': 'Carlos Ruiz', 'correo_electronico': 'carlos@gmail.com', 'contrasena_hash': 'hash_13', 'rol': 'CLIENTE', 'esta_activo': True, 'fecha_creacion': '2026-10-22T10:45:00'},
    {'_id': 14, 'nombre': 'Andres Castro', 'correo_electronico': 'andres@gmail.com', 'contrasena_hash': 'hash_14', 'rol': 'CLIENTE', 'esta_activo': True, 'fecha_creacion': '2026-10-22T11:00:00'},
    {'_id': 20, 'nombre': 'Chef Roberto (El Rincon)', 'correo_electronico': 'roberto@rincon.com', 'contrasena_hash': 'hash_20', 'rol': 'CHEF', 'esta_activo': True, 'fecha_creacion': '2026-10-22T08:00:00'},
    {'_id': 21, 'nombre': 'Chef Mario (Burger Station)', 'correo_electronico': 'mario@burger.com', 'contrasena_hash': 'hash_21', 'rol': 'CHEF', 'esta_activo': True, 'fecha_creacion': '2026-10-22T08:30:00'},
    {'_id': 22, 'nombre': 'Chef Luigi (Bella Italia)', 'correo_electronico': 'luigi@bellaitalia.com', 'contrasena_hash': 'hash_22', 'rol': 'CHEF', 'esta_activo': True, 'fecha_creacion': '2026-10-22T09:00:00'},
    {'_id': 23, 'nombre': 'Chef Chen (Wok Express)', 'correo_electronico': 'chen@wokexpress.com', 'contrasena_hash': 'hash_23', 'rol': 'CHEF', 'esta_activo': True, 'fecha_creacion': '2026-10-22T09:30:00'},
    {'_id': 99, 'nombre': 'Admin SaborLocal', 'correo_electronico': 'admin@saborlocal.com', 'contrasena_hash': 'hash_admin', 'rol': 'ADMIN', 'esta_activo': True, 'fecha_creacion': '2026-10-01T00:00:00'}
])

# 2. RESTAURANTES
db.restaurantes.insert_many([
    {'_id': 10, 'usuario_id': 20, 'nombre_restaurante': 'El Rincon Criollo', 'direccion': 'Carrera 7 #12-45', 'descripcion': 'Comida tradicional y criolla', 'estado': 'PUBLICADO', 'hora_apertura': '08:00', 'hora_cierre': '20:00', 'fecha_creacion': '2026-10-22T08:10:00'},
    {'_id': 11, 'usuario_id': 21, 'nombre_restaurante': 'Burger Station', 'direccion': 'Calle 15 #8-30', 'descripcion': 'Hamburguesas artesanales', 'estado': 'PUBLICADO', 'hora_apertura': '11:00', 'hora_cierre': '23:00', 'fecha_creacion': '2026-10-22T08:40:00'},
    {'_id': 12, 'usuario_id': 22, 'nombre_restaurante': 'Pizzeria Bella Italia', 'direccion': 'Avenida 4 #18-20', 'descripcion': 'Pastas y pizzas en horno de lena', 'estado': 'PUBLICADO', 'hora_apertura': '12:00', 'hora_cierre': '22:00', 'fecha_creacion': '2026-10-22T09:10:00'},
    {'_id': 13, 'usuario_id': 23, 'nombre_restaurante': 'Wok Express', 'direccion': 'Calle 10 #5-50', 'descripcion': 'Comida asiatica y sushi', 'estado': 'PUBLICADO', 'hora_apertura': '11:30', 'hora_cierre': '21:30', 'fecha_creacion': '2026-10-22T09:40:00'}
])

# 3. PRODUCTOS
db.productos.insert_many([
    # El Rincon Criollo (restaurante_id: 10)
    {'_id': 10, 'restaurante_id': 10, 'nombre': 'Bandeja Paisa', 'descripcion': 'Frijoles, chicharron, carne molida, huevo y tajada', 'precio': 28, 'inventario': 20, 'esta_activo': True, 'fecha_creacion': '2026-10-22T08:15:00'},
    {'_id': 11, 'restaurante_id': 10, 'nombre': 'Sancocho de Gallina', 'descripcion': 'Sancocho tradicional con arroz y aguacate', 'precio': 20, 'inventario': 15, 'esta_activo': True, 'fecha_creacion': '2026-10-22T08:20:00'},
    {'_id': 12, 'restaurante_id': 10, 'nombre': 'Ajiaco Santafereso', 'descripcion': 'Con pollo, mazorca y alcaparras', 'precio': 22, 'inventario': 12, 'esta_activo': True, 'fecha_creacion': '2026-10-22T08:25:00'},
    # Burger Station (restaurante_id: 11)
    {'_id': 20, 'restaurante_id': 11, 'nombre': 'Hamburguesa Doble Queso', 'descripcion': '200g carne de res, queso cheddar y tocino', 'precio': 24, 'inventario': 30, 'esta_activo': True, 'fecha_creacion': '2026-10-22T08:45:00'},
    {'_id': 21, 'restaurante_id': 11, 'nombre': 'Papas BBQ Especiales', 'descripcion': 'Papas en cascos con salsa BBQ y queso fundido', 'precio': 12, 'inventario': 40, 'esta_activo': True, 'fecha_creacion': '2026-10-22T08:50:00'},
    {'_id': 22, 'restaurante_id': 11, 'nombre': 'Malteada de Chocolate', 'descripcion': 'Con crema batida y chispas', 'precio': 10, 'inventario': 25, 'esta_activo': True, 'fecha_creacion': '2026-10-22T08:55:00'},
    # Bella Italia (restaurante_id: 12)
    {'_id': 30, 'restaurante_id': 12, 'nombre': 'Pizza Pepperoni Familiar', 'descripcion': 'Masa delgada con queso mozzarella y pepperoni', 'precio': 35, 'inventario': 18, 'esta_activo': True, 'fecha_creacion': '2026-10-22T09:15:00'},
    {'_id': 31, 'restaurante_id': 12, 'nombre': 'Lasaña Bolonesa', 'descripcion': 'Capas de pasta con carne y queso gratinado', 'precio': 26, 'inventario': 10, 'esta_activo': True, 'fecha_creacion': '2026-10-22T09:20:00'},
    # Wok Express (restaurante_id: 13)
    {'_id': 40, 'restaurante_id': 13, 'nombre': 'Arroz Chaufa Especial', 'descripcion': 'Arroz salteado con pollo, carne y camarones', 'precio': 27, 'inventario': 22, 'esta_activo': True, 'fecha_creacion': '2026-10-22T09:45:00'},
    {'_id': 41, 'restaurante_id': 13, 'nombre': 'Roll California (10 pcs)', 'descripcion': 'Sushi con cangrejo, aguacate y pepino', 'precio': 30, 'inventario': 15, 'esta_activo': True, 'fecha_creacion': '2026-10-22T09:50:00'}
])

# 4. PEDIDOS
db.pedidos.insert_many([
    {'_id': 100, 'cliente_id': 10, 'restaurante_id': 10, 'tipo_entrega': 'DOMICILIO', 'direccion_entrega': 'Calle 20 #5-12', 'subtotal': 48, 'monto_comision': 4.8, 'monto_total': 52.8, 'estado': 'ENTREGADO', 'items': [{'producto_id': 10, 'cantidad': 1}, {'producto_id': 11, 'cantidad': 1}], 'fecha_creacion': '2026-10-22T11:30:00', 'fecha_actualizacion': '2026-10-22T12:15:00'},
    {'_id': 101, 'cliente_id': 11, 'restaurante_id': 11, 'tipo_entrega': 'RECOGER', 'direccion_entrega': None, 'subtotal': 36, 'monto_comision': 3.6, 'monto_total': 39.6, 'estado': 'ENTREGADO', 'items': [{'producto_id': 20, 'cantidad': 1}, {'producto_id': 21, 'cantidad': 1}], 'fecha_creacion': '2026-10-22T11:45:00', 'fecha_actualizacion': '2026-10-22T12:20:00'},
    {'_id': 102, 'cliente_id': 12, 'restaurante_id': 12, 'tipo_entrega': 'DOMICILIO', 'direccion_entrega': 'Carrera 15 #2-80', 'subtotal': 35, 'monto_comision': 3.5, 'monto_total': 38.5, 'estado': 'EN_PREPARACION', 'items': [{'producto_id': 30, 'cantidad': 1}], 'fecha_creacion': '2026-10-22T12:00:00', 'fecha_actualizacion': '2026-10-22T12:10:00'},
    {'_id': 103, 'cliente_id': 13, 'restaurante_id': 13, 'tipo_entrega': 'DOMICILIO', 'direccion_entrega': 'Calle 8 #11-04', 'subtotal': 57, 'monto_comision': 5.7, 'monto_total': 62.7, 'estado': 'PENDIENTE', 'items': [{'producto_id': 40, 'cantidad': 1}, {'producto_id': 41, 'cantidad': 1}], 'fecha_creacion': '2026-10-22T12:30:00', 'fecha_actualizacion': '2026-10-22T12:30:00'},
    {'_id': 104, 'cliente_id': 14, 'restaurante_id': 11, 'tipo_entrega': 'DOMICILIO', 'direccion_entrega': 'Avenida 6 #14-22', 'subtotal': 34, 'monto_comision': 3.4, 'monto_total': 37.4, 'estado': 'CANCELADO', 'items': [{'producto_id': 20, 'cantidad': 1}, {'producto_id': 22, 'cantidad': 1}], 'fecha_creacion': '2026-10-22T12:40:00', 'fecha_actualizacion': '2026-10-22T12:45:00'}
])

# 5. PAGOS
db.pagos.insert_many([
    {'_id': 100, 'pedido_id': 100, 'metodo_pago': 'TARJETA_CREDITO', 'monto': 52.8, 'referencia_pago': 'Visa **** 4412', 'fecha_pago': '2026-10-22T11:31:00', 'confirmacion': {'estado': 'APROBADO', 'codigo': 'TX_100'}},
    {'_id': 101, 'pedido_id': 101, 'metodo_pago': 'NEQUI', 'monto': 39.6, 'referencia_pago': 'Nequi 3110009988', 'fecha_pago': '2026-10-22T11:46:00', 'confirmacion': {'estado': 'APROBADO', 'codigo': 'NQ_101'}},
    {'_id': 102, 'pedido_id': 102, 'metodo_pago': 'PSE', 'monto': 38.5, 'referencia_pago': 'Bancolombia PSE 9981', 'fecha_pago': '2026-10-22T12:01:00', 'confirmacion': {'estado': 'APROBADO', 'codigo': 'PSE_102'}},
    {'_id': 103, 'pedido_id': 103, 'metodo_pago': 'EFECTIVO', 'monto': 62.7, 'referencia_pago': 'Pago contra entrega', 'fecha_pago': '2026-10-22T12:30:00', 'confirmacion': {'estado': 'PENDIENTE', 'codigo': 'EF_103'}}
])

# 6. RECIBOS
db.recibos.insert_many([
    {'_id': 100, 'pedido_id': 100, 'contenido': 'RECIBO #100 - El Rincon Criollo. Total: .8 USD. Gracias por preferir SaborLocal.', 'fecha_generacion': '2026-10-22T11:31:05'},
    {'_id': 101, 'pedido_id': 101, 'contenido': 'RECIBO #101 - Burger Station. Total: .6 USD. Gracias por preferir SaborLocal.', 'fecha_generacion': '2026-10-22T11:46:05'},
    {'_id': 102, 'pedido_id': 102, 'contenido': 'RECIBO #102 - Pizzeria Bella Italia. Total: .5 USD. Gracias por preferir SaborLocal.', 'fecha_generacion': '2026-10-22T12:01:05'}
])

# 7. CALIFICACIONES
db.calificaciones.insert_many([
    {'_id': 100, 'pedido_id': 100, 'puntuacion': 5, 'comentario': 'La Bandeja Paisa estaba deliciosa y llego muy caliente.', 'fecha_creacion': '2026-10-22T12:30:00'},
    {'_id': 101, 'pedido_id': 101, 'puntuacion': 4, 'comentario': 'Muy buenas las papas y la hamburguesa, buena atencion al recoger.', 'fecha_creacion': '2026-10-22T12:40:00'}
])

# 8. HISTORIAL DE ESTADOS
db.historial_estados.insert_many([
    {'_id': 1, 'pedido_id': 100, 'actor_id': 10, 'evento': 'PEDIDO_CREADO', 'detalle': 'Pedido registrado', 'fecha': '2026-10-22T11:30:00'},
    {'_id': 2, 'pedido_id': 100, 'actor_id': 20, 'evento': 'EN_PREPARACION', 'detalle': 'Cocinando platos', 'fecha': '2026-10-22T11:35:00'},
    {'_id': 3, 'pedido_id': 100, 'actor_id': 20, 'evento': 'PEDIDO_ENTREGADO', 'detalle': 'Entregado a domiciliario', 'fecha': '2026-10-22T12:15:00'},
    {'_id': 4, 'pedido_id': 102, 'actor_id': 12, 'evento': 'PEDIDO_CREADO', 'detalle': 'Pedido registrado', 'fecha': '2026-10-22T12:00:00'},
    {'_id': 5, 'pedido_id': 102, 'actor_id': 22, 'evento': 'EN_PREPARACION', 'detalle': 'Pizza al horno', 'fecha': '2026-10-22T12:10:00'},
    {'_id': 6, 'pedido_id': 104, 'actor_id': 14, 'evento': 'PEDIDO_CANCELADO', 'detalle': 'Cliente cancelo la orden', 'fecha': '2026-10-22T12:45:00'}
])

print('¡Base de datos saborlocal poblada masivamente con exito!')