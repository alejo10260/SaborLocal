class CartService:
    """Servicio independiente para la gestión de ítems y cálculos del carrito."""
    
    @staticmethod
    def agregar_o_actualizar_item(carrito, producto, cantidad):
        if cantidad <= 0:
            return False, "La cantidad debe ser mayor a cero.", carrito

        stock_disponible = producto.get('inventario', 0)
        
        # Buscar si ya está en el carrito
        item_existente = next((item for item in carrito if item['producto_id'] == str(producto['_id'])), None)
        cantidad_actual = item_existente['cantidad'] if item_existente else 0
        
        if (cantidad_actual + cantidad) > stock_disponible:
            return False, f"Stock insuficiente. Solo quedan {stock_disponible} disponibles.", carrito

        subtotal = producto['precio'] * cantidad

        if item_existente:
            item_existente['cantidad'] += cantidad
            item_existente['subtotal'] += subtotal
        else:
            carrito.append({
                'producto_id': str(producto['_id']),
                'nombre': producto['nombre'],
                'precio': producto['precio'],
                'cantidad': cantidad,
                'subtotal': subtotal
            })

        return True, "Producto agregado correctamente.", carrito

    @staticmethod
    def calcular_totales(carrito):
        subtotal = sum(item['subtotal'] for item in carrito)
        comision = subtotal * 0.10  # 10% de servicio
        total = subtotal + comision
        return {
            "items": carrito,
            "subtotal": subtotal,
            "comision": comision,
            "total": total,
            "cantidad_items": sum(item['cantidad'] for item in carrito)
        }