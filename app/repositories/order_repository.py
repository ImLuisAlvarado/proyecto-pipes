from uuid import UUID
from sqlalchemy.sql import func
from app.extensions import db
from app.models.order import Order, OrderRefill, OrderItem
from datetime import datetime

class OrderRepository:
    
    @staticmethod
    def get_by_id(order_id: UUID) -> Order:
        """Busca una orden con todos sus items y refills precargados."""
        return Order.query.get(order_id)

    @staticmethod
    def create_order(order_model: Order, initial_items: list[OrderItem]) -> Order:
        """Guarda la orden principal y sus items iniciales en una sola transacción."""
        db.session.add(order_model)
        db.session.flush()  # Genera el UUID de la orden antes de guardarla en los items
        
        for item in initial_items:
            item.order_id = order_model.id
            db.session.add(item)
            
        db.session.commit()
        return order_model

    @staticmethod
    def add_refill_round(order_id: UUID, created_by: UUID, reason: str, items: list[OrderItem]) -> OrderRefill:
        """Registra una nueva ronda de refills calculando el consecutivo automático."""
        # 1. Calcular el siguiente número de refill (refill_no) para esta orden específica
        max_refill = db.session.query(func.max(OrderRefill.refill_no))\
            .filter(OrderRefill.order_id == order_id).scalar()
        
        next_refill_no = (max_refill or 0) + 1
        
        # 2. Crear la cabecera del refill
        refill = OrderRefill(
            order_id=order_id,
            created_by=created_by,
            reason=reason,
            refill_no=next_refill_no
        )
        db.session.add(refill)
        db.session.flush()  # Genera el ID del refill
        
        # 3. Vincular los nuevos items a la orden y a esta ronda de refill
        for item in items:
            item.order_id = order_id
            item.refill_id = refill.id
            item.is_refill = True  # Forzamos la bandera de tu esquema
            db.session.add(item)
            
        db.session.commit()
        return refill

    @staticmethod
    def update_order_totals(order_id: UUID) -> Order:
        """
        Recalcula matemáticamente el subtotal, impuestos y total de la orden
        basándose en la suma de sus order_items actuales.
        """
        order = Order.query.get(order_id)
        if not order:
            return None
            
        # Obtenemos todos los items vigentes de la orden
        items = OrderItem.query.filter(OrderItem.order_id == order_id).all()
        
        subtotal = 0
        tax_total = 0
        
        for item in items:
            # qty y unit_price son Decimal gracias a los esquemas
            item_subtotal = item.qty * item.unit_price
            item_tax = item_subtotal * (item.tax_rate / 100)
            
            subtotal += item_subtotal
            tax_total += item_tax
            
        order.subtotal = subtotal
        order.tax_total = tax_total
        # total = subtotal + tax - discounts (asumiendo descuento 0 inicial)
        order.total = (subtotal + tax_total) - order.discount_total
        
        db.session.commit()
        return order
    
    @staticmethod
    def close_order(order_id: UUID, closed_by: UUID) -> Order:
        """Marca la orden como cerrada y registra la hora exacta."""
        order = Order.query.get(order_id)
        if order:
            order.status = 'closed'
            order.closed_by = closed_by
            # marca la hora de cierre en PostgreSQL
            order.closed_at = datetime.utcnow() 
            db.session.commit()
        return order