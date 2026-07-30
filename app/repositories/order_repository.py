# app/repositories/order_repository.py
from uuid import UUID
from datetime import datetime
from sqlalchemy.sql import func
from app.extensions import db
from app.models.order import Order, OrderRefill, OrderItem


class OrderRepository:

    @staticmethod
    def list_orders(branch_id=None, status=None) -> list[Order]:
        q = Order.query
        if branch_id:
            q = q.filter_by(branch_id=branch_id)
        if status:
            q = q.filter_by(status=status)
        return q.order_by(Order.opened_at.desc()).all()

    @staticmethod
    def get_by_id(order_id: UUID) -> Order:
        return Order.query.get(order_id)

    @staticmethod
    def create_order(order_model: Order, initial_items: list[OrderItem]) -> Order:
        db.session.add(order_model)
        db.session.flush()
        for item in initial_items:
            item.order_id = order_model.id
            db.session.add(item)
        db.session.commit()
        return order_model

    @staticmethod
    def add_items(order_id: UUID, items: list[OrderItem]) -> None:
        for item in items:
            item.order_id = order_id
            db.session.add(item)
        db.session.commit()

    @staticmethod
    def update_status(order_id: UUID, status: str) -> Order:
        order = Order.query.get(order_id)
        if order:
            order.status = status
            db.session.commit()
        return order

    @staticmethod
    def save() -> None:
        db.session.commit()

    @staticmethod
    def get_refills(order_id: UUID) -> list[OrderRefill]:
        return OrderRefill.query\
            .filter_by(order_id=order_id)\
            .order_by(OrderRefill.refill_no.asc())\
            .all()

    @staticmethod
    def add_refill_round(order_id: UUID, created_by: UUID,
                         reason: str, items: list[OrderItem]) -> OrderRefill:
        max_no = db.session.query(func.max(OrderRefill.refill_no))\
            .filter(OrderRefill.order_id == order_id).scalar()
        next_no = (max_no or 0) + 1

        refill = OrderRefill(
            order_id=order_id,
            created_by=created_by,
            reason=reason,
            refill_no=next_no,
        )
        db.session.add(refill)
        db.session.flush()

        for item in items:
            item.order_id  = order_id
            item.refill_id = refill.id
            item.is_refill = True
            db.session.add(item)

        db.session.commit()
        return refill

    @staticmethod
    def update_order_totals(order_id: UUID) -> Order:
        order = Order.query.get(order_id)
        if not order:
            return None
        items = OrderItem.query.filter_by(order_id=order_id).all()
        subtotal = tax_total = 0
        for item in items:
            line     = item.qty * item.unit_price
            subtotal += line
            tax_total += line * (item.tax_rate / 100)
        order.subtotal  = subtotal
        order.tax_total = tax_total
        order.total     = (subtotal + tax_total) - order.discount_total
        db.session.commit()
        return order

    @staticmethod
    def delete_order_item(order_id: UUID, item_id: UUID) -> OrderItem | None:
        item = OrderItem.query.filter_by(order_id=order_id, id=item_id).first()
        if not item:
            return None
        db.session.delete(item)
        db.session.commit()
        return item

    @staticmethod
    def transfer_order(order_id: UUID, old_table_id: UUID, new_table_id: UUID) -> Order:
        from app.models.core import DiningTable
        order = Order.query.get(order_id)
        if not order:
            return None

        order.table_id = new_table_id

        old_table = DiningTable.query.get(old_table_id)
        if old_table:
            old_table.status = 'available'

        new_table = DiningTable.query.get(new_table_id)
        if new_table:
            new_table.status = 'occupied'

        db.session.commit()
        return order

    @staticmethod
    def close_order(order_id: UUID, closed_by) -> Order:
        order = Order.query.get(order_id)
        if order:
            order.status    = 'closed'
            order.closed_by = closed_by
            order.closed_at = datetime.utcnow()
            db.session.commit()
        return order