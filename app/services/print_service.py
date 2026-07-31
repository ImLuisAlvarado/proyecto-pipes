# app/services/print_service.py
"""
Servicio de impresión.
Construye el payload del ticket, crea el PrintJob en la DB
y lo despacha por TCP a la impresora correspondiente.
"""
import socket
import json
from datetime import datetime
from collections import defaultdict

from app.extensions import db
from app.models.order import Order, OrderItem, PrintJob
from app.models.core import DiningTable, Printer
from app.models.product import Product
from app.printer_simulation import add_ticket_from_payload


class PrintService:

    def dispatch_kitchen_ticket(self, order: Order) -> list[PrintJob]:
        print(f">>> dispatch_kitchen_ticket orden={order.id} branch={order.branch_id}")
        jobs = []

        items_by_station: dict[str, list[OrderItem]] = {}
        for item in order.items:
            items_by_station.setdefault(item.station, []).append(item)

        print(f">>> stations en items: {list(items_by_station.keys())}")
        print(f">>> total items: {len(order.items)}")

        table = DiningTable.query.get(order.table_id)
        table_code = table.code if table else '?'

        for station, items in items_by_station.items():
            printer = Printer.query.filter_by(
                branch_id=order.branch_id,
                station=station,
                active=True
            ).first()
            print(f">>> buscando impresora para station='{station}' → {printer}")

            if not printer:
                print(f">>> sin impresora para station={station}, saltando")
                continue

            try:
                payload = self._build_kitchen_payload(order, table_code, items)
                print(f">>> payload construido OK")
            except Exception as e:
                print(f">>> ERROR en _build_kitchen_payload: {e}")
                continue

            try:
                job = self._create_print_job(order, printer, 'kitchen', payload)
                print(f">>> PrintJob creado: {job.id}")
            except Exception as e:
                print(f">>> ERROR en _create_print_job: {e}")
                import traceback
                traceback.print_exc()
                continue

            self._send_job(job, printer, mode='json')
            jobs.append(job)

        return jobs
    
    def dispatch_refill_ticket(self, order: Order, refill_items: list[OrderItem]) -> list[PrintJob]:
        print(f">>> dispatch_refill_ticket orden={order.id} items={len(refill_items)}")
        jobs = []

        table = DiningTable.query.get(order.table_id)
        table_code = table.code if table else '?'

        grouped: dict[tuple[str, str], list[OrderItem]] = defaultdict(list)
        for item in refill_items:
            station = item.station or 'default'
            seat = item.seat_label or 'Mesa'
            grouped[(station, seat)].append(item)

        for (station, seat), items in grouped.items():
            printer = Printer.query.filter_by(
                branch_id=order.branch_id,
                station=station,
                active=True
            ).first()

            if not printer:
                print(f">>> sin impresora para station={station}, saltando")
                continue

            try:
                payload = self._build_refill_payload(order, table_code, items)
                payload['seat_label'] = seat
            except Exception as e:
                print(f">>> ERROR en _build_refill_payload: {e}")
                continue

            try:
                job = self._create_print_job(order, printer, 'kitchen', payload)
                print(f">>> PrintJob refill creado: {job.id}")
            except Exception as e:
                print(f">>> ERROR en _create_print_job: {e}")
                continue

            self._send_job(job, printer, mode='json')
            jobs.append(job)

        return jobs

    def _build_refill_payload(self, order: Order, table_code: str, items: list[OrderItem]) -> dict:
        seats: dict[str, list] = {}
        for item in items:
            seat = item.seat_label or 'Mesa'
            product = Product.query.get(item.product_id)
            seats.setdefault(seat, []).append({
                'qty': float(item.qty),
                'name': product.name if product else str(item.product_id),
                'notes': item.notes or '',
            })

        return {
            'type': 'refill',
            'order_id': str(order.id),
            'table_code': table_code,
            'time': datetime.now().strftime('%H:%M'),
            'order_notes': order.notes or '',
            'seats': seats,
        }

    def dispatch_cashier_ticket(self, order: Order, payment_method: str = 'N/A') -> PrintJob | None:
        """Genera el ticket de caja (cierre) y lo envía a la impresora de tipo cashier."""
        printer = Printer.query.filter_by(
            branch_id=order.branch_id,
            type='cashier',
            active=True
        ).first()

        if not printer:
            return None

        table = DiningTable.query.get(order.table_id)
        table_code = table.code if table else '?'

        payload = self._build_cashier_payload(order, table_code, payment_method)
        text_payload = self._format_cashier_ticket_as_text(payload)
        job = self._create_print_job(order, printer, 'cashier', payload)
        self._send_job(job, printer, mode='text', text_payload=text_payload)
        return job

    def build_cashier_bill(self, order: Order) -> dict:
        table = DiningTable.query.get(order.table_id)
        table_label = table.code if table and getattr(table, 'code', None) else str(order.table_id)

        # Group items by seat_label
        seats = {}
        subtotal = 0.0

        for item in order.items:
            product = Product.query.get(item.product_id)
            qty = float(item.qty)
            unit_price = float(item.unit_price)
            line_total = qty * unit_price
            subtotal += line_total

            seat = item.seat_label or 'Mesa'
            seats.setdefault(seat, []).append({
                'product_id': str(item.product_id),
                'name': product.name if product else str(item.product_id),
                'qty': qty,
                'unit_price': unit_price,
                'total': line_total,
                'notes': item.notes or '',
                'seat_label': seat,
                'print_station': item.station or 'cashier',
            })

        tax = float(order.tax_total) if order.tax_total is not None else 0.0
        total = float(order.total) if order.total is not None else subtotal + tax

        return {
            'order_id': str(order.id),
            'branch_id': str(order.branch_id),
            'table_id': str(order.table_id),
            'table_code': table_label,
            'order_number': getattr(order, 'order_number', None),
            'seats': seats,
            'subtotal': subtotal,
            'tax': tax,
            'total': total,
            'print_station': 'cashier',
            'status': 'bill_printed',
        }

    def dispatch_cashier_bill(self, order: Order, bill: dict) -> PrintJob | None:
        print(f">>> dispatch_cashier_bill orden={order.id} branch={order.branch_id}")

        printer = Printer.query.filter_by(
            branch_id=order.branch_id,
            type='cashier',
            active=True
        ).first()

        print(f">>> cashier printer={printer}")

        if not printer:
            print(">>> no cashier printer found")
            return None

        payload = self._format_bill_as_text(bill)
        print(f">>> bill payload length={len(payload)}")

        job = self._create_print_job(order, printer, 'cashier_bill', bill)
        print(f">>> PrintJob creado: {job.id}")

        self._send_job(job, printer, mode='text', text_payload=payload)
        return job

    def _build_kitchen_payload(self, order: Order, table_code: str, items: list[OrderItem]) -> dict:
        seats: dict[str, list] = {}
        for item in items:
            seat = item.seat_label or 'Mesa'
            product = Product.query.get(item.product_id)
            seats.setdefault(seat, []).append({
                'qty': float(item.qty),
                'name': product.name if product else str(item.product_id),
                'notes': item.notes or '',
            })

        return {
            'type': 'kitchen',
            'order_id': str(order.id),
            'table_code': table_code,
            'time': datetime.now().strftime('%H:%M'),
            'order_notes': order.notes or '',
            'seats': seats,
        }

    def _build_cashier_payload(self, order: Order, table_code: str, payment_method: str) -> dict:
        # Group items by seat_label for the closing ticket
        seats = {}
        subtotal = 0.0

        for item in order.items:
            product = Product.query.get(item.product_id)
            qty = float(item.qty)
            unit_price = float(item.unit_price)
            line_total = qty * unit_price
            subtotal += line_total

            seat = item.seat_label or 'Mesa'
            seats.setdefault(seat, []).append({
                'qty': qty,
                'name': product.name if product else str(item.product_id),
                'unit_price': unit_price,
                'total': line_total,
                'notes': item.notes or '',
            })

        tax = float(order.tax_total) if order.tax_total is not None else 0.0
        total = float(order.total) if order.total is not None else subtotal + tax

        return {
            'type': 'cashier',
            'order_id': str(order.id),
            'table_code': table_code,
            'date': datetime.now().strftime('%d/%m/%Y'),
            'time': datetime.now().strftime('%H:%M'),
            'seats': seats,
            'subtotal': subtotal,
            'tax_total': tax,
            'total': total,
            'payment_method': payment_method,
        }

    def _format_cashier_ticket_as_text(self, payload: dict) -> str:
        """Formats a cashier closing ticket as text for printing with seat grouping"""
        lines = []
        sep = "=" * 40
        dash = "-" * 40

        lines.append(sep)
        lines.append(f"{'PIPES DESDE 1989':^40}")
        lines.append(sep)
        lines.append(f"Mesa: {payload.get('table_code', '?')}")
        lines.append(f"Orden: {str(payload.get('order_id', '?'))[:8]}...")
        lines.append(f"Fecha: {payload.get('date', '?')}")
        lines.append(f"Hora: {payload.get('time', '?')}")
        lines.append(dash)
        
        # Display items grouped by seat
        for seat, items in payload.get('seats', {}).items():
            lines.append(f"Cliente: {seat}")
            lines.append(dash)

            for item in items:
                qty = float(item.get('qty', 0))
                name = str(item.get('name', '?'))
                notes = str(item.get('notes', '')).strip()
                total = float(item.get('total', 0))
                lines.append(f"{qty:g}x {name:<22} ${total:>8.2f}")
                if notes:
                    lines.append(f"   > {notes}")
            lines.append(dash)
        
        lines.append(f"{'Subtotal':<30} ${float(payload.get('subtotal', 0)):>8.2f}")
        lines.append(f"{'IVA':<30} ${float(payload.get('tax_total', 0)):>8.2f}")
        lines.append(f"{'TOTAL':<30} ${float(payload.get('total', 0)):>8.2f}")
        lines.append(f"{'Pago con':<30} {payload.get('payment_method', 'N/A')}")
        lines.append(dash)
        lines.append(f"{'¡Gracias por su visita!':^40}")
        lines.append(sep)
        
        return "\n".join(lines)

    def _format_bill_as_text(self, bill: dict) -> str:
        lines = []
        sep = "=" * 40
        dash = "-" * 40

        lines.append(sep)
        lines.append(f"{'PIPES DESDE 1989':^40}")
        lines.append(sep)
        lines.append(f"Mesa: {bill.get('table_code', '?')}")
        lines.append(f"Orden: {str(bill.get('order_id', '?'))[:8]}...")
        lines.append(dash)
        
        for seat, items in bill.get('seats', {}).items():
            lines.append(f"Cliente: {seat}")
            lines.append(dash)

            for item in items:
                qty = float(item.get('qty', 0))
                name = str(item.get('name', '?'))
                notes = str(item.get('notes', '')).strip()
                total = float(item.get('total', 0))
                lines.append(f"{qty:g}x {name:<22} ${total:>8.2f}")
                if notes:
                    lines.append(f"   > {notes}")
            lines.append(dash)
        lines.append(f"{'Subtotal':<30} ${float(bill.get('subtotal', 0)):>8.2f}")
        lines.append(f"{'IVA':<30} ${float(bill.get('tax', 0)):>8.2f}")
        lines.append(f"{'TOTAL':<30} ${float(bill.get('total', 0)):>8.2f}")
        lines.append(dash)
        lines.append(f"{'¡Gracias por su visita!':^40}")
        lines.append(sep)
        return "\n".join(lines)

    def _create_print_job(self, order: Order, printer: Printer, job_type: str, payload: dict) -> PrintJob:
        job = PrintJob(
            branch_id=order.branch_id,
            order_id=order.id,
            printer_id=printer.id,
            job_type=job_type,
            status='pending',
            payload=payload,
            attempts=0,
        )
        db.session.add(job)
        db.session.commit()
        return job

    def _send_job(self, job: PrintJob, printer: Printer, mode: str = 'json', text_payload: str | None = None) -> None:
        print(f">>> _send_job printer={printer.ip_address}:{printer.port} job={job.id} mode={mode}")
        try:
            if mode == 'text' and text_payload is not None:
                data = text_payload.encode('utf-8')
            else:
                data = json.dumps(job.payload).encode('utf-8')

            ticket_payload = job.payload if isinstance(job.payload, dict) else {'raw': job.payload}
            ticket_type = ticket_payload.get('type') or job.job_type or printer.station
            ticket_station = printer.station or 'kitchen'
            add_ticket_from_payload(
                ticket_payload,
                ticket_station,
                raw_size=len(data),
                from_ip='print-service',
                ticket_type=ticket_type,
            )

            print(f">>> intentando TCP a {printer.ip_address}:{printer.port} ({len(data)} bytes)")
            with socket.create_connection((str(printer.ip_address), printer.port), timeout=5) as sock:
                sock.sendall(data)
                print(f">>> enviado correctamente")

            job.status = 'synced'
            job.sent_at = datetime.utcnow()
        except Exception as e:
            print(f">>> ERROR TCP: {e}")
            job.status = 'failed'
            job.last_error = str(e)
            job.attempts += 1

        db.session.commit()