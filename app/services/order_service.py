# app/services/order_service.py
from uuid import UUID
from flask import abort
from app.repositories.order_repository import OrderRepository
from app.models.order import Order, OrderItem
from app.schemas.order import OrderCreate, OrderRefillCreate, OrderItemCreate
from app.services.print_service import PrintService
from decimal import Decimal


class OrderService:

    def __init__(self):
        self.repo = OrderRepository()

    # ── listar ─────────────────────────────────────────────────────────────
    def list_orders(self, branch_id=None, status=None) -> list[Order]:
        return self.repo.list_orders(branch_id=branch_id, status=status)

    # ── obtener una ────────────────────────────────────────────────────────
    def get_order_by_id(self, order_id: UUID) -> Order:
        order = self.repo.get_by_id(order_id)
        if not order:
            abort(404, description="La orden especificada no existe.")
        return order

    # ── crear ──────────────────────────────────────────────────────────────
    def create_new_order(self, data: OrderCreate) -> Order:
        new_order = Order(
            branch_id=data.branch_id,
            table_id=data.table_id,
            opened_by=data.opened_by,
            customer_id=data.customer_id,
            notes=data.notes,
            status='open',
        )
        items = [self._to_item(s) for s in data.items]
        order = self.repo.create_order(new_order, items)
        if items:
            order = self.repo.update_order_totals(order.id)
        return order

    # ── actualización parcial ──────────────────────────────────────────────
    def update_order(self, order_id: UUID, fields: dict) -> Order:
        order = self.get_order_by_id(order_id)
        allowed = {'notes', 'customer_id', 'status'}
        for key, value in fields.items():
            if key in allowed:
                setattr(order, key, value)
        self.repo.save()
        return order

    # ── agregar items ──────────────────────────────────────────────────────
    def add_items_to_order(self, order_id: UUID, schemas: list[OrderItemCreate]) -> Order:
        order = self.get_order_by_id(order_id)
        if order.status in ('closed', 'cancelled'):
            abort(400, description=f"La orden está {order.status}.")
        items = [self._to_item(s) for s in schemas]
        self.repo.add_items(order_id, items)
        return self.repo.update_order_totals(order_id)


    def delete_order_item(self, order_id: UUID, item_id: UUID):
        order = self.get_order_by_id(order_id)
        item = self.repo.delete_order_item(order_id, item_id)
        if not item:
            abort(404, description="El item no existe en esa orden.")
        self.repo.update_order_totals(order_id)
        return order

    # ── enviar a cocina ────────────────────────────────────────────────────
    def send_to_kitchen(self, order_id: UUID) -> Order:

        order = self.get_order_by_id(order_id)
        if order.status in ('closed', 'cancelled'):
            abort(400, description=f"La orden está {order.status}.")

        order = self.repo.update_status(order_id, 'sent')

        try:
            PrintService().dispatch_kitchen_ticket(order)
        except Exception as e:
            print(f">>> WARN: dispatch_kitchen_ticket falló: {e}")

        return order


    def update_order_item(self, order_id: UUID, item_id: UUID, fields: dict) -> Order:
        order = self.get_order_by_id(order_id)
        item = next((i for i in order.items if str(i.id) == str(item_id)), None)
        if not item:
            abort(404, description="El item no existe en esa orden.")

        allowed = {
            "seat_label",
            "qty",
            "unit_price",
            "tax_rate",
            "notes",
            "station",
            "is_refill",
        }

        for key, value in fields.items():
            if key not in allowed:
                continue
            if key in {"qty", "unit_price", "tax_rate"} and value is not None:
                value = Decimal(str(value))
            if key == "is_refill" and value is not None:
                value = bool(value)
            setattr(item, key, value)

        self.repo.save()
        return self.repo.get_by_id(order_id)

    # ── imprimir cuenta (pre-cobro) ───────────────────────────────────────
    def print_bill(self, order_id: UUID) -> dict:
        from app.services.print_service import PrintService
        order = self.get_order_by_id(order_id)
        if order.status in ('closed', 'cancelled'):
            abort(400, description=f"La orden está {order.status}.")
        service = PrintService()
        bill    = service.build_cashier_bill(order)
        try:
            service.dispatch_cashier_bill(order, bill)
        except Exception as e:
            print(f">>> WARN: dispatch_cashier_bill falló: {e}")
        return bill

    # ── refills ────────────────────────────────────────────────────────────
    def get_refills(self, order_id: UUID):
        self.get_order_by_id(order_id)
        return self.repo.get_refills(order_id)

    def request_order_refill(self, order_id: UUID, data: OrderRefillCreate) -> Order:

        order = self.get_order_by_id(order_id)
        if order.status in ('closed', 'cancelled'):
            abort(400, description=f"La orden está {order.status}.")

        refill_items = [self._to_item(s, is_refill=True) for s in data.items]

        self.repo.add_refill_round(
            order_id=order_id,
            created_by=data.created_by,
            reason=data.reason,
            items=refill_items,
        )

        order = self.repo.update_order_totals(order_id)

        try:
            PrintService().dispatch_refill_ticket(order, refill_items)
        except Exception as e:
            print(f">>> WARN: dispatch_refill_ticket falló: {e}")

        return order

    # ── transferir mesa ────────────────────────────────────────────────────
    def transfer_order(self, order_id: UUID, new_table_id: UUID) -> Order:
        from app.models.core import DiningTable
        order = self.get_order_by_id(order_id)
        if order.status in ('closed', 'cancelled'):
            abort(400, description=f"No se puede transferir una orden {order.status}.")
        new_table = DiningTable.query.get(new_table_id)
        if not new_table:
            abort(404, description="Mesa destino no encontrada.")
        return self.repo.transfer_order(order_id, order.table_id, new_table_id)

    # ── cerrar ─────────────────────────────────────────────────────────────
    def close_account(self, order_id: UUID, closed_by, payment_method: str = 'N/A') -> Order:
        from app.services.print_service import PrintService
        order = self.get_order_by_id(order_id)
        if order.status in ('closed', 'cancelled'):
            abort(400, description=f"La orden ya está {order.status}.")
        order = self.repo.close_order(order_id, closed_by)
        try:
            PrintService().dispatch_cashier_ticket(order, payment_method)
        except Exception as e:
            print(f">>> WARN: dispatch_cashier_ticket falló: {e}")
        return order

    # ── helper ─────────────────────────────────────────────────────────────
    @staticmethod
    def _to_item(s: OrderItemCreate, is_refill: bool = False) -> OrderItem:
        return OrderItem(
            product_id=s.product_id,
            qty=s.qty,
            unit_price=s.unit_price,
            tax_rate=s.tax_rate,
            notes=s.notes,
            station=s.station,
            seat_label=s.seat_label,
            is_refill=s.is_refill or is_refill,
        )