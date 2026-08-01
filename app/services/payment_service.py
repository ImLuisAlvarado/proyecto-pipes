from uuid import UUID
from flask import abort
from app.extensions import db
from app.models.order import Payment, Order, OrderItem
from app.schemas.payment import PaymentCreate


class PaymentService:

    def create_payment(self, order_id: UUID, schema: PaymentCreate) -> Payment:
        order = Order.query.get(order_id)
        if not order:
            abort(404, description="Orden no encontrada.")
        if order.status == 'cancelled':
            abort(400, description="No se puede cobrar una orden cancelada.")

        received_by = schema.received_by or order.opened_by

        payment = Payment(
            branch_id=order.branch_id,
            order_id=order_id,
            method=schema.method,
            amount=schema.amount,
            tip_amount=schema.tip_amount,
            received_amount=schema.received_amount,
            change_amount=schema.change_amount,
            seat_labels=schema.seat_labels,
            received_by=received_by,
            notes=schema.notes,
        )
        db.session.add(payment)
        db.session.commit()

        try:
            self._dispatch_payment_ticket(order, payment, schema)
        except Exception as e:
            print(f">>> WARN: dispatch_payment_ticket falló: {e}")

        return payment

    def get_payments_by_order(self, order_id: UUID) -> list[Payment]:
        return Payment.query.filter_by(order_id=order_id).all()

    def _dispatch_payment_ticket(self, order: Order, payment: Payment,
                                 schema: PaymentCreate) -> None:
        from app.models.core import DiningTable, Printer
        import socket, json
        from datetime import datetime

        printer = Printer.query.filter_by(
            branch_id=order.branch_id,
            type='cashier',
            active=True
        ).first()

        if not printer:
            print(">>> WARN: No hay impresora de caja activa para el ticket de pago")
            return

        table = DiningTable.query.get(order.table_id)
        table_code = table.code if table else '?'

        payload = self._build_payment_ticket_payload(order, payment, schema, table_code)

        from app.models.order import PrintJob
        job = PrintJob(
            branch_id=order.branch_id,
            order_id=order.id,
            printer_id=printer.id,
            job_type='cashier',
            status='pending',
            payload=payload,
            attempts=0,
        )
        db.session.add(job)
        db.session.commit()

        try:
            data = json.dumps(payload).encode('utf-8')
            with socket.create_connection((str(printer.ip_address), printer.port), timeout=5) as sock:
                sock.sendall(data)
            job.status = 'synced'
            job.sent_at = datetime.utcnow()
        except Exception as e:
            job.status = 'failed'
            job.last_error = str(e)
            job.attempts += 1
            print(f">>> ERROR TCP pago: {e}")

        db.session.commit()

    def _build_payment_ticket_payload(self, order: Order, payment: Payment,
                                      schema: PaymentCreate,
                                      table_code: str) -> dict:
        from datetime import datetime
        from app.models.product import Product
        from app.models.core import Customer

        seat_labels = schema.seat_labels or []
        all_items = list(order.items)

        table_subtotal = sum(float(i.qty) * float(i.unit_price) for i in all_items)
        table_tax = sum(
            float(i.qty) * float(i.unit_price) * (float(i.tax_rate) / 100)
            for i in all_items
        )

        if seat_labels:
            items = [
                item for item in all_items
                if (item.seat_label or '1') in seat_labels
            ]
        else:
            items = all_items

        seats_data: dict[str, list] = {}
        seat_totals: dict[str, float] = {}
        client_subtotal = 0.0
        client_tax = 0.0

        for item in items:
            seat = item.seat_label or '1'
            product = Product.query.get(item.product_id)
            line_total = float(item.qty) * float(item.unit_price)
            line_tax = line_total * (float(item.tax_rate) / 100)
            client_subtotal += line_total
            client_tax += line_tax
            seat_totals[seat] = seat_totals.get(seat, 0.0) + line_total + line_tax

            seats_data.setdefault(seat, []).append({
                'qty': float(item.qty),
                'name': product.name if product else str(item.product_id),
                'unit_price': float(item.unit_price),
                'total': line_total,
                'notes': item.notes or '',
            })

        is_partial = bool(seat_labels) and len(seat_labels) < len(
            {(i.seat_label or '1') for i in all_items}
        )

        change = float(schema.change_amount) if schema.change_amount is not None else 0.0
        received_amount = (
            float(schema.received_amount)
            if schema.received_amount is not None
            else None
        )

        customer_name = None
        if order.customer_id:
            customer = Customer.query.get(order.customer_id)
            customer_name = customer.full_name.strip() if customer and customer.full_name else None

        return {
            'type': 'payment_receipt',
            'order_id': str(order.id),
            'table_code': table_code,
            'date': datetime.now().strftime('%d/%m/%Y'),
            'time': datetime.now().strftime('%H:%M'),
            'customer_name': customer_name,
            'client_name': customer_name,
            'is_partial': is_partial,
            'seat_labels': seat_labels,
            'seats': seats_data,
            'seat_totals': seat_totals,
            'table_subtotal': float(table_subtotal),
            'table_tax': float(table_tax),
            'subtotal': float(client_subtotal),
            'tax': float(client_tax),
            'tip': float(schema.tip_amount),
            'total': float(payment.amount),
            'payment_method': payment.method,
            'method': payment.method,
            'received_amount': received_amount,
            'change_amount': change,
        }