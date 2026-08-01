"""
printer_simulator.py
====================
Simulador de impresoras ESC/POS para desarrollo — evolucionando hacia
dashboard de reportería para producción.

Levanta DOS servidores TCP (cocina y caja) y una interfaz web con:
  - Vista de tickets en tiempo real
  - Cierre de caja por período / método / sucursal
  - Reporte de ventas por producto / categoría
  - Comparativa día vs día anterior

Persistencia: JSON local (sales_store.json), con una capa de acceso
a datos aislada (SalesStore) para facilitar una futura migración a
PostgreSQL sin tocar la lógica de reportes.
"""

import socket
import threading
import json
import re
import os
import csv
import io
from datetime import datetime, timedelta
from collections import defaultdict
from flask import Blueprint, render_template_string, jsonify, request, Response

printer_bp = Blueprint("printer_simulator", __name__)
tickets = []
tickets_lock = threading.Lock()

KITCHEN_PORT = 9100
CASHIER_PORT = 9101
WEB_PORT = 8080
SALES_FILE = "sales_store.json"


class SalesStore:
    def __init__(self, path):
        self._path = path
        self._lock = threading.Lock()
        self._data = []
        self._load()

    def _load(self):
        if os.path.exists(self._path):
            try:
                with open(self._path, "r", encoding="utf-8") as f:
                    self._data = json.load(f)
            except Exception:
                self._data = []

    def _save(self):
        with open(self._path, "w", encoding="utf-8") as f:
            json.dump(self._data, f, ensure_ascii=False, indent=2)

    def add(self, sale):
        with self._lock:
            self._data.insert(0, sale)
            self._save()

    def all(self):
        with self._lock:
            return list(self._data)

    def clear(self):
        with self._lock:
            self._data.clear()
            self._save()

    def filtered(self, from_date=None, to_date=None, method=None, branch=None):
        rows = self.all()
        if from_date:
            rows = [s for s in rows if s["date"] >= from_date]
        if to_date:
            rows = [s for s in rows if s["date"] <= to_date]
        if method:
            rows = [s for s in rows if s.get("payment_method") == method]
        if branch:
            rows = [s for s in rows if str(s.get("branch", "")).lower() == branch.lower()]
        return rows


sales_store = SalesStore(SALES_FILE)


def money(value):
    try:
        return float(value or 0)
    except Exception:
        return 0.0


def payment_method_label(value):
    return {
        "cash": "Efectivo",
        "card": "Tarjeta",
        "transfer": "Transferencia",
        "mixed": "Mixto",
    }.get(value or "", value or "N/A")


def customer_name_from_payload(payload):
    return (
        payload.get("customer_name")
        or payload.get("client_name")
        or payload.get("customer")
        or payload.get("client")
        or ""
    )


def parse_escpos(data):
    result = data
    result = re.sub(rb'\x1b[@!Eam][\x00-\xff]?', b'', result)
    result = re.sub(rb'\x1d[Vh][\x00-\xff]?', b'', result)
    result = re.sub(rb'\x1b\x61[\x00-\x02]', b'', result)
    result = re.sub(rb'\x1b\x21[\x00-\xff]', b'', result)
    result = re.sub(rb'\x1d\x21[\x00-\xff]', b'', result)
    result = re.sub(rb'[\x00-\x08\x0b-\x0c\x0e-\x1f\x7f]', b'', result)
    try:
        return result.decode('utf-8', errors='replace')
    except Exception:
        return result.decode('latin-1', errors='replace')


def extract_line_items(payload):
    lines = []

    for item in payload.get("items", []):
        qty = money(item.get("qty", 1))
        unit_price = money(item.get("unit_price"))
        total = money(item.get("total", qty * unit_price))
        lines.append({
            "name": item.get("name", "?"),
            "category": item.get("category") or item.get("print_station") or "Sin categoría",
            "qty": qty,
            "unit_price": unit_price,
            "total": total,
        })

    for seat_label, items in payload.get("seats", {}).items():
        for item in items:
            qty = money(item.get("qty", 1))
            unit_price = money(item.get("unit_price"))
            total = money(item.get("total", qty * unit_price))
            lines.append({
                "name": item.get("name", "?"),
                "category": item.get("category") or "Sin categoría",
                "qty": qty,
                "unit_price": unit_price,
                "total": total,
            })

    return lines


def normalize_sale(payload, station):
    now = datetime.now()
    payment_method = payload.get("payment_method") or payload.get("method") or "N/A"
    branch = payload.get("branch") or payload.get("branch_name") or "principal"
    line_items = extract_line_items(payload)
    customer_name = customer_name_from_payload(payload)

    return {
        "id": None,
        "timestamp": now.isoformat(timespec="seconds"),
        "date": now.strftime("%Y-%m-%d"),
        "time": now.strftime("%H:%M:%S"),
        "station": station,
        "branch": branch,
        "ticket_type": payload.get("type", station),
        "order_id": payload.get("order_id"),
        "table_code": payload.get("table_code"),
        "customer_name": customer_name,
        "client_name": customer_name,
        "payment_method": payment_method,
        "payment_method_label": payment_method_label(payment_method),
        "subtotal": money(payload.get("subtotal")),
        "tax": money(payload.get("tax", payload.get("tax_total"))),
        "tip": money(payload.get("tip")),
        "total": money(payload.get("total")),
        "received_amount": payload.get("received_amount"),
        "change_amount": payload.get("change_amount"),
        "items": line_items,
        "closed": False,
        "raw_payload": payload,
    }


def should_store_sale(payload, ticket_type):
    return ticket_type in ("cashier_bill", "payment_receipt", "cashier")


def add_sale(sale):
    sale["id"] = len(sales_store.all()) + 1
    sales_store.add(sale)


def build_summary(rows):
    by_method = defaultdict(float)
    for s in rows:
        by_method[s.get("payment_method", "N/A")] += money(s.get("total"))

    return {
        "count": len(rows),
        "subtotal": sum(money(s.get("subtotal")) for s in rows),
        "tax": sum(money(s.get("tax")) for s in rows),
        "tip": sum(money(s.get("tip")) for s in rows),
        "total": sum(money(s.get("total")) for s in rows),
        "by_method": {
            "cash": by_method.get("cash", 0.0),
            "card": by_method.get("card", 0.0),
            "transfer": by_method.get("transfer", 0.0),
            "mixed": by_method.get("mixed", 0.0),
        }
    }


def build_product_report(rows, group_by="name"):
    agg = defaultdict(lambda: {"qty": 0.0, "total": 0.0, "count": 0})

    for sale in rows:
        for item in sale.get("items", []):
            key = item.get(group_by) or "Sin datos"
            agg[key]["qty"] += item.get("qty", 0)
            agg[key]["total"] += item.get("total", 0)
            agg[key]["count"] += 1

    result = [
        {"name": k, "qty": v["qty"], "total": v["total"], "lines": v["count"]}
        for k, v in agg.items()
    ]
    result.sort(key=lambda r: r["qty"], reverse=True)
    return result


def build_day_comparison(target_date, branch=None):
    if target_date:
        day = datetime.strptime(target_date, "%Y-%m-%d").date()
    else:
        day = datetime.now().date()

    prev_day = day - timedelta(days=1)

    today_rows = sales_store.filtered(
        from_date=day.isoformat(), to_date=day.isoformat(), branch=branch
    )
    prev_rows = sales_store.filtered(
        from_date=prev_day.isoformat(), to_date=prev_day.isoformat(), branch=branch
    )

    today_summary = build_summary(today_rows)
    prev_summary = build_summary(prev_rows)

    def pct_change(curr, prev):
        if prev == 0:
            return None if curr == 0 else 100.0
        return round(((curr - prev) / prev) * 100, 1)

    return {
        "today_date": day.isoformat(),
        "previous_date": prev_day.isoformat(),
        "today": today_summary,
        "previous": prev_summary,
        "delta": {
            "total_pct": pct_change(today_summary["total"], prev_summary["total"]),
            "count_pct": pct_change(today_summary["count"], prev_summary["count"]),
            "tip_pct": pct_change(today_summary["tip"], prev_summary["tip"]),
        }
    }


def format_ticket_from_payload(payload, station):
    lines = []
    sep = "=" * 40
    dash = "-" * 40
    ticket_type = payload.get("type", station)

    if ticket_type in ("kitchen", "refill"):
        header = "REFILL" if ticket_type == "refill" else "COCINA"
        lines.append(sep)
        lines.append("{:^40}".format(header))
        lines.append(sep)
        lines.append("Mesa: {:>32}".format(payload.get("table_code", "?")))
        lines.append("Orden: {}...  {}".format(payload.get("order_id", "?")[:8], payload.get("time", "")))

        order_notes = (payload.get("order_notes") or "").strip()
        if order_notes:
            lines.append(dash)
            lines.append("  *** NOTA ORDEN: {}".format(order_notes))

        lines.append(dash)
        for seat_label, items in payload.get("seats", {}).items():
            lines.append("  Comensal {}:".format(seat_label))
            for item in items:
                qty = item.get("qty", 1)
                name = item.get("name", "?")
                item_notes = item.get("notes", "").strip()
                lines.append("    {}x {}".format(qty, name))
                if item_notes:
                    lines.append("       *** {}".format(item_notes))
            lines.append("")
        lines.append(sep)

    elif ticket_type == "cashier":
        customer_name = customer_name_from_payload(payload)
        payment_method = payload.get("payment_method") or payload.get("method") or "N/A"
        lines.append(sep)
        lines.append("{:^40}".format("PIPES DESDE 1989"))
        lines.append("{:^40}".format("VOUCHER"))
        lines.append(sep)
        lines.append("Mesa: {:>32}".format(payload.get("table_code", "?")))
        lines.append("Orden: {}...".format(payload.get("order_id", "?")[:8]))
        if customer_name:
            lines.append("Cliente: {}".format(customer_name))
        lines.append("Fecha: {}  {}".format(payload.get("date", ""), payload.get("time", "")))
        lines.append(dash)
        for seat_label, items in payload.get("seats", {}).items():
            lines.append("  -- Cliente {} --".format(seat_label))
            for item in items:
                qty = item.get("qty", 1)
                name = str(item.get("name", "?"))[:20]
                total = money(item.get("total"))
                notes = str(item.get("notes", "")).strip()
                lines.append("  {:<3} {:<22} ${:>7.2f}".format(qty, name, total))
                if notes:
                    lines.append("       * {}".format(notes))
            seat_total = money((payload.get("seat_totals") or {}).get(seat_label, 0))
            lines.append("  {:<28} ${:>7.2f}".format("Monto cliente", seat_total))
            lines.append(dash)
        lines.append("  {:<28} ${:>7.2f}".format("Subtotal", money(payload.get("subtotal"))))
        lines.append("  {:<28} ${:>7.2f}".format("IVA", money(payload.get("tax_total") or payload.get("tax"))))
        lines.append("  {:<28} ${:>7.2f}".format("TOTAL", money(payload.get("total"))))
        lines.append("  {:<28} {}".format("Metodo pago", payment_method_label(payment_method)))
        lines.append(sep)
        lines.append("{:^40}".format("¡Gracias por su visita!"))
        lines.append(sep)

    elif ticket_type == "cashier_bill":
        customer_name = customer_name_from_payload(payload)
        seat_labels = payload.get("seat_labels") or []
        payment_method = payload.get("payment_method") or payload.get("method") or "N/A"
        lines.append(sep)
        lines.append("{:^40}".format("PIPES DESDE 1989"))
        lines.append("{:^40}".format("CUENTA"))
        lines.append(sep)
        lines.append("Mesa: {:>32}".format(payload.get("table_code", "?")))
        lines.append("Orden: {}...".format(payload.get("order_id", "?")[:8]))
        if customer_name:
            lines.append("Cliente: {}".format(customer_name))
        if seat_labels:
            lines.append("Comensales: {}".format(", ".join(seat_labels)))
        lines.append(dash)
        for seat_label, items in payload.get("seats", {}).items():
            lines.append("  -- Cliente {} --".format(seat_label))
            for item in items:
                qty = item.get("qty", 1)
                name = str(item.get("name", "?"))[:20]
                total = money(item.get("total"))
                notes = str(item.get("notes", "")).strip()
                lines.append("  {:<3} {:<22} ${:>7.2f}".format(qty, name, total))
                if notes:
                    lines.append("       * {}".format(notes))
            seat_total = money((payload.get("seat_totals") or {}).get(seat_label, 0))
            lines.append("  {:<28} ${:>7.2f}".format("Monto cliente", seat_total))
            lines.append(dash)
        lines.append("  {:<28} ${:>7.2f}".format("Subtotal", money(payload.get("subtotal"))))
        lines.append("  {:<28} ${:>7.2f}".format("IVA", money(payload.get("tax"))))
        lines.append("  {:<28} ${:>7.2f}".format("TOTAL", money(payload.get("total"))))
        lines.append("  {:<28} {}".format("Metodo pago", payment_method_label(payment_method)))
        lines.append(sep)

    elif ticket_type == "payment_receipt":
        is_partial = payload.get("is_partial", False)
        seat_labels = payload.get("seat_labels", [])
        customer_name = customer_name_from_payload(payload)
        payment_method = payload.get("payment_method") or payload.get("method") or "N/A"
        header = "PAGO PARCIAL" if is_partial else "COMPROBANTE DE PAGO"
        lines.append(sep)
        lines.append("{:^40}".format("PIPES DESDE 1989"))
        lines.append("{:^40}".format(header))
        lines.append(sep)
        lines.append("Mesa: {:>32}".format(payload.get("table_code", "?")))
        if customer_name:
            lines.append("Cliente: {}".format(customer_name))
        if is_partial and seat_labels:
            lines.append("Comensales: {}".format(", ".join(seat_labels)))
        lines.append("Fecha: {}  {}".format(payload.get("date", ""), payload.get("time", "")))
        lines.append(dash)
        for seat_label, items in payload.get("seats", {}).items():
            lines.append("  -- Comensal {} --".format(seat_label))
            for item in items:
                qty = item.get("qty", 1)
                name = str(item.get("name", "?"))[:20]
                total = money(item.get("total"))
                notes = item.get("notes", "").strip()
                lines.append("  {:<3} {:<22} ${:>7.2f}".format(qty, name, total))
                if notes:
                    lines.append("       * {}".format(notes))
            seat_total = money((payload.get("seat_totals") or {}).get(seat_label, 0))
            lines.append("  {:<28} ${:>7.2f}".format("Monto cliente", seat_total))
            lines.append(dash)
        lines.append("  {:<28} ${:>7.2f}".format("IVA", money(payload.get("tax"))))
        lines.append("  {:<28} ${:>7.2f}".format("Total de este cliente", money(payload.get("total"))))
        tip = money(payload.get("tip"))
        if tip > 0:
            lines.append("  {:<28} ${:>7.2f}".format("Propina", tip))
        lines.append(dash)
        lines.append("  {:<28} ${:>7.2f}".format("Subtotal de la mesa", money(payload.get("table_subtotal"))))
        lines.append(dash)
        lines.append("  Metodo: {}".format(payment_method_label(payment_method)))
        received = payload.get("received_amount")
        change = payload.get("change_amount")
        if received is not None:
            lines.append("  {:<28} ${:>7.2f}".format("Recibido", money(received)))
        lines.append("  {:<28} ${:>7.2f}".format("Su cambio", money(change)))
        lines.append(sep)
        lines.append("{:^40}".format("¡Gracias por su visita!"))
        lines.append(sep)

    else:
        customer_name = customer_name_from_payload(payload)
        lines.append(sep)
        lines.append("{:^40}".format("PIPES DESDE 1989"))
        lines.append(sep)
        lines.append("Mesa: {:>32}".format(payload.get("table_code", "?")))
        lines.append("Orden: {}...".format(payload.get("order_id", "?")[:8]))
        if customer_name:
            lines.append("Cliente: {}".format(customer_name))
        lines.append("Fecha: {}".format(payload.get("date", datetime.now().strftime("%d/%m/%Y"))))
        lines.append(dash)
        lines.append("{:<5} {:<22} {:>8}".format("Cant", "Producto", "Total"))
        lines.append(dash)
        for item in payload.get("items", []):
            qty = item.get("qty", 1)
            name = str(item.get("name", "?"))[:20]
            price = money(item.get("unit_price"))
            subtotal = qty * price
            lines.append("  {:<3} {:<22} ${:>7.2f}".format(qty, name, subtotal))
        lines.append(dash)
        lines.append("  {:<28} ${:>7.2f}".format("Subtotal", money(payload.get("subtotal"))))
        lines.append("  {:<28} ${:>7.2f}".format("IVA", money(payload.get("tax_total"))))
        lines.append("  {:<28} ${:>7.2f}".format("TOTAL", money(payload.get("total"))))
        lines.append(dash)
        lines.append("  Método pago: {}".format(payload.get("payment_method", "N/A")))
        lines.append(sep)
        lines.append("{:^40}".format("¡Gracias por su visita!"))
        lines.append(sep)

    return "\n".join(lines)


def handle_connection(conn, addr, station):
    with conn:
        chunks = []
        while True:
            chunk = conn.recv(4096)
            if not chunk:
                break
            chunks.append(chunk)

        raw = b"".join(chunks)
        if not raw:
            return

        payload_data = None
        try:
            payload_data = json.loads(raw.decode("utf-8"))
            ticket_type = payload_data.get("type", station)
            text_content = format_ticket_from_payload(payload_data, station)
        except Exception:
            ticket_type = station
            text_content = parse_escpos(raw)

        ui_type = ticket_type if ticket_type in (
            "kitchen", "refill", "cashier", "cashier_bill", "payment_receipt"
        ) else station

        ticket = {
            "id": len(tickets) + 1,
            "station": station,
            "ticket_type": ui_type,
            "timestamp": datetime.now().strftime("%H:%M:%S"),
            "date": datetime.now().strftime("%d/%m/%Y"),
            "content": text_content,
            "raw_size": len(raw),
            "from_ip": addr[0],
        }

        with tickets_lock:
            tickets.insert(0, ticket)
            if len(tickets) > 50:
                tickets.pop()

        if payload_data is not None and should_store_sale(payload_data, ticket_type):
            sale = normalize_sale(payload_data, station)
            add_sale(sale)

        print("[{}] Ticket desde {} — {} bytes".format(ui_type.upper(), addr[0], len(raw)))


def tcp_server(port, station):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind(("0.0.0.0", port))
        s.listen(5)
        print("[{}] Escuchando en puerto {}...".format(station.upper(), port))
        while True:
            conn, addr = s.accept()
            threading.Thread(target=handle_connection, args=(conn, addr, station), daemon=True).start()


HTML = """
<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Simulador de Impresoras — POS</title>
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
               background: #f0f2f5; color: #1a1a2e; min-height: 100vh; }
        header { background: #1a1a2e; color: white; padding: 16px 24px;
                 display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 12px; }
        header h1 { font-size: 18px; font-weight: 600; }
        .status { display: flex; gap: 16px; flex-wrap: wrap; }
        .dot { display: inline-flex; align-items: center; gap: 6px; font-size: 13px; }
        .dot::before { content: ''; width: 8px; height: 8px; border-radius: 50%;
                       background: #4caf50; display: inline-block; animation: pulse 2s infinite; }
        @keyframes pulse { 0%,100%{opacity:1} 50%{opacity:0.4} }
        .tabs { padding: 0 24px; background: white; border-bottom: 1px solid #e0e0e0;
                display: flex; gap: 4px; flex-wrap: wrap; }
        .tab { padding: 12px 16px; cursor: pointer; font-size: 13px; font-weight: 500;
               color: #6b7280; border-bottom: 2px solid transparent; }
        .tab.active { color: #1a1a2e; border-bottom-color: #1a1a2e; }
        .toolbar { padding: 12px 24px; background: white; border-bottom: 1px solid #e0e0e0;
                   display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
        .btn { padding: 6px 14px; border-radius: 6px; border: none; cursor: pointer;
               font-size: 13px; font-weight: 500; }
        .btn-clear { background: #fee2e2; color: #dc2626; }
        .filter-btn { background: #f3f4f6; color: #374151; }
        .filter-btn.active { background: #1a1a2e; color: white; }
        .secondary-btn { background: #e0e7ff; color: #3730a3; }
        .count { font-size: 12px; color: #6b7280; margin-left: auto; }
        .container { padding: 20px 24px; display: grid;
                     grid-template-columns: repeat(auto-fill, minmax(320px, 1fr)); gap: 16px; }
        .view { display: none; }
        .view.active { display: block; }
        .ticket, .panel { background: white; border-radius: 10px; overflow: hidden;
                          box-shadow: 0 1px 3px rgba(0,0,0,0.1); }
        .ticket-header { padding: 10px 14px; display: flex; justify-content: space-between; align-items: center; }
        .ticket-header.kitchen  { background: #fef3c7; border-bottom: 2px solid #f59e0b; }
        .ticket-header.refill    { background: #fce7f3; border-bottom: 2px solid #ec4899; }
        .ticket-header.cashier   { background: #dbeafe; border-bottom: 2px solid #3b82f6; }
        .ticket-header.cashier_bill { background: #dcfce7; border-bottom: 2px solid #22c55e; }
        .ticket-header.payment_receipt { background: #ede9fe; border-bottom: 2px solid #8b5cf6; }
        .badge { font-size: 11px; font-weight: 600; text-transform: uppercase;
                 letter-spacing: 0.05em; padding: 2px 8px; border-radius: 4px; color: white; }
        .kitchen .badge { background: #f59e0b; }
        .refill .badge { background: #ec4899; }
        .cashier .badge { background: #3b82f6; }
        .cashier_bill .badge { background: #22c55e; }
        .payment_receipt .badge { background: #8b5cf6; }
        .ticket-meta { font-size: 11px; color: #6b7280; }
        .ticket-content, .panel-content {
            padding: 14px; font-family: 'Courier New', monospace;
            font-size: 12px; line-height: 1.6; white-space: pre-wrap;
            background: #fafafa; border-top: 1px solid #f0f0f0;
            max-height: 400px; overflow-y: auto;
        }
        .ticket-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(320px, 1fr)); gap: 16px; }
        .report-form { padding: 14px; display: grid; gap: 10px; background: white; }
        .row { display: grid; grid-template-columns: repeat(auto-fit, minmax(160px, 1fr)); gap: 10px; }
        label { font-size: 12px; font-weight: 600; color: #374151; display: block; margin-bottom: 4px; }
        input, select {
            width: 100%; padding: 8px 10px; border: 1px solid #d1d5db;
            border-radius: 6px; font-size: 13px;
        }
        table { width: 100%; border-collapse: collapse; font-size: 12px; margin-top: 10px; }
        th, td { padding: 8px 6px; border-bottom: 1px solid #e5e7eb; text-align: left; }
        th { background: #f9fafb; }
        .summary {
            display: grid; grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
            gap: 10px; margin-top: 10px;
        }
        .metric {
            background: #f9fafb; border: 1px solid #e5e7eb; border-radius: 8px; padding: 10px;
        }
        .metric .label { font-size: 11px; color: #6b7280; }
        .metric .value { font-size: 18px; font-weight: 700; margin-top: 4px; }
        .metric .delta { font-size: 12px; font-weight: 600; margin-top: 2px; }
        .delta.up { color: #16a34a; }
        .delta.down { color: #dc2626; }
        .delta.flat { color: #6b7280; }
        .compare-cols { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; margin-top: 10px; }
        .compare-col { background: #f9fafb; border: 1px solid #e5e7eb; border-radius: 8px; padding: 12px; }
        .compare-col h4 { font-size: 12px; color: #6b7280; margin-bottom: 8px; text-transform: uppercase; }
        .empty { grid-column: 1/-1; text-align: center; padding: 60px 20px; color: #9ca3af; }
        .empty-icon { font-size: 48px; margin-bottom: 12px; }
        .bar-row { display: flex; align-items: center; gap: 8px; margin-bottom: 6px; }
        .bar-label { width: 140px; font-size: 12px; flex-shrink: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
        .bar-track { flex: 1; height: 16px; background: #f3f4f6; border-radius: 4px; overflow: hidden; }
        .bar-fill { height: 100%; background: #8b5cf6; }
        .bar-value { width: 80px; text-align: right; font-size: 12px; font-weight: 600; flex-shrink: 0; }
    </style>
</head>
<body>
    <header>
        <h1>Simulador de Impresoras — POS</h1>
        <div class="status">
            <span class="dot">Cocina :9100</span>
            <span class="dot">Caja :9101</span>
        </div>
    </header>

    <div class="tabs">
        <div class="tab active" data-view="tickets" onclick="switchTab('tickets', this)">Tickets en vivo</div>
        <div class="tab" data-view="close" onclick="switchTab('close', this)">Cierre de caja</div>
        <div class="tab" data-view="products" onclick="switchTab('products', this)">Ventas por producto</div>
        <div class="tab" data-view="compare" onclick="switchTab('compare', this)">Comparativa diaria</div>
    </div>

    <div class="view active" id="view-tickets">
        <div class="toolbar">
            <button class="btn filter-btn active" onclick="setFilter('all', this)">Todos</button>
            <button class="btn filter-btn" onclick="setFilter('kitchen', this)">Cocina</button>
            <button class="btn filter-btn" onclick="setFilter('refill', this)">Refill</button>
            <button class="btn filter-btn" onclick="setFilter('cashier_bill', this)">Cuenta</button>
            <button class="btn filter-btn" onclick="setFilter('payment_receipt', this)">Recibo</button>
            <button class="btn filter-btn" onclick="setFilter('cashier', this)">Voucher</button>
            <button class="btn btn-clear" onclick="clearTickets()">Limpiar tickets</button>
            <span class="count" id="countLabel">0 tickets</span>
        </div>
        <div class="container ticket-grid" id="ticketContainer">
            <div class="empty" id="emptyState">
                <div class="empty-icon">🖨️</div>
                <p>Esperando tickets...</p>
            </div>
        </div>
    </div>

    <div class="view" id="view-close">
        <div class="container" style="grid-template-columns: 1fr;">
            <div class="panel">
                <div class="ticket-header cashier_bill">
                    <div><span class="badge">CIERRE</span></div>
                    <div class="ticket-meta">Reporte de ventas</div>
                </div>
                <div class="report-form">
                    <div class="row">
                        <div><label>Fecha inicial</label><input type="date" id="fromDate"></div>
                        <div><label>Fecha final</label><input type="date" id="toDate"></div>
                        <div>
                            <label>Método de pago</label>
                            <select id="methodFilter">
                                <option value="">Todos</option>
                                <option value="cash">Efectivo</option>
                                <option value="card">Tarjeta</option>
                                <option value="transfer">Transferencia</option>
                                <option value="mixed">Mixto</option>
                            </select>
                        </div>
                        <div><label>Sucursal</label><input type="text" id="branchFilter" placeholder="principal"></div>
                    </div>
                    <div>
                        <button class="btn secondary-btn" onclick="generateReport()">Generar reporte</button>
                        <button class="btn secondary-btn" onclick="exportCsv()">Exportar CSV</button>
                        <button class="btn secondary-btn" onclick="printClose()">Imprimir cierre</button>
                        <button class="btn btn-clear" onclick="clearSales()">Limpiar ventas</button>
                    </div>
                </div>
                <div class="panel-content" id="reportContent">Selecciona filtros y genera un reporte.</div>
            </div>
        </div>
    </div>

    <div class="view" id="view-products">
        <div class="container" style="grid-template-columns: 1fr;">
            <div class="panel">
                <div class="ticket-header payment_receipt">
                    <div><span class="badge">PRODUCTOS</span></div>
                    <div class="ticket-meta">Ranking de ventas</div>
                </div>
                <div class="report-form">
                    <div class="row">
                        <div><label>Fecha inicial</label><input type="date" id="prodFromDate"></div>
                        <div><label>Fecha final</label><input type="date" id="prodToDate"></div>
                        <div>
                            <label>Agrupar por</label>
                            <select id="prodGroupBy">
                                <option value="name">Producto</option>
                                <option value="category">Categoría / Estación</option>
                            </select>
                        </div>
                        <div><label>Sucursal</label><input type="text" id="prodBranchFilter" placeholder="principal"></div>
                    </div>
                    <div>
                        <button class="btn secondary-btn" onclick="generateProductReport()">Generar reporte</button>
                    </div>
                </div>
                <div class="panel-content" id="productReportContent">Selecciona filtros y genera un reporte.</div>
            </div>
        </div>
    </div>

    <div class="view" id="view-compare">
        <div class="container" style="grid-template-columns: 1fr;">
            <div class="panel">
                <div class="ticket-header cashier">
                    <div><span class="badge">COMPARATIVA</span></div>
                    <div class="ticket-meta">Día vs día anterior</div>
                </div>
                <div class="report-form">
                    <div class="row">
                        <div><label>Día a comparar</label><input type="date" id="compareDate"></div>
                        <div><label>Sucursal</label><input type="text" id="compareBranchFilter" placeholder="principal"></div>
                    </div>
                    <div>
                        <button class="btn secondary-btn" onclick="generateComparison()">Comparar</button>
                    </div>
                </div>
                <div class="panel-content" id="compareContent">Selecciona una fecha y genera la comparativa.</div>
            </div>
        </div>
    </div>

    <script>
        let allTickets = [], currentFilter = 'all', lastCount = 0;

        function switchTab(view, tabEl) {
            document.querySelectorAll('.tab').forEach(function(t){ t.classList.remove('active'); });
            document.querySelectorAll('.view').forEach(function(v){ v.classList.remove('active'); });
            tabEl.classList.add('active');
            document.getElementById('view-' + view).classList.add('active');

            if (view === 'close' && !document.getElementById('fromDate').value) {
                var today = new Date().toISOString().split('T')[0];
                document.getElementById('fromDate').value = today;
                document.getElementById('toDate').value = today;
                generateReport();
            }
            if (view === 'compare' && !document.getElementById('compareDate').value) {
                document.getElementById('compareDate').value = new Date().toISOString().split('T')[0];
                generateComparison();
            }
        }

        function setFilter(f, btn) {
            currentFilter = f;
            document.querySelectorAll('.filter-btn').forEach(function(b){ b.classList.remove('active'); });
            btn.classList.add('active');
            renderTickets();
        }

        function renderTickets() {
            var filtered = currentFilter === 'all'
                ? allTickets
                : allTickets.filter(function(t){ return t.ticket_type === currentFilter; });

            var container = document.getElementById('ticketContainer');
            document.getElementById('countLabel').textContent = filtered.length + ' tickets';

            if (filtered.length === 0) {
                container.innerHTML = '<div class="empty"><div class="empty-icon">🖨️</div><p>Sin tickets para este filtro</p></div>';
                return;
            }
            container.innerHTML = filtered.map(function(t) {
                return '<div class="ticket">' +
                    '<div class="ticket-header ' + (t.ticket_type || t.station) + '">' +
                        '<div><span class="badge">' + (t.ticket_type || t.station) + '</span></div>' +
                        '<div class="ticket-meta">#' + t.id + ' · ' + t.date + ' ' + t.timestamp + '</div>' +
                    '</div>' +
                    '<div class="ticket-content">' + escapeHtml(t.content) + '</div>' +
                '</div>';
            }).join('');
        }

        function escapeHtml(t) {
            return (t || '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
        }

        function clearTickets() {
            fetch('/api/clear', {method:'POST'}).then(function(){ allTickets = []; renderTickets(); });
        }

        function poll() {
            fetch('/api/tickets').then(function(r){ return r.json(); }).then(function(data) {
                if (data.length !== lastCount) {
                    allTickets = data;
                    lastCount = data.length;
                    renderTickets();
                    if (data.length > 0) {
                        document.title = '● Nuevo ticket — POS';
                        setTimeout(function(){ document.title = 'Simulador de Impresoras — POS'; }, 3000);
                    }
                }
            }).catch(function(){});
        }
        setInterval(poll, 1500);
        poll();

        function getParams() {
            var params = new URLSearchParams();
            var from = document.getElementById('fromDate').value;
            var to = document.getElementById('toDate').value;
            var method = document.getElementById('methodFilter').value;
            var branch = document.getElementById('branchFilter').value;
            if (from) params.append('from', from);
            if (to) params.append('to', to);
            if (method) params.append('method', method);
            if (branch) params.append('branch', branch);
            return params;
        }

        function clearSales() {
            fetch('/api/clear-sales', {method:'POST'}).then(function(){
                document.getElementById('reportContent').textContent = 'Ventas borradas.';
            });
        }

        function generateReport() {
            fetch('/api/sales?' + getParams().toString())
                .then(function(r){ return r.json(); })
                .then(function(data) {
                    var report = data.report;
                    var rows = data.sales.map(function(s) {
                        return '<tr>' +
                            '<td>' + s.date + ' ' + s.time + '</td>' +
                            '<td>' + (s.branch || '-') + '</td>' +
                            '<td>' + (s.table_code || '-') + '</td>' +
                            '<td>' + (s.payment_method_label || s.payment_method) + '</td>' +
                            '<td>$' + Number(s.subtotal || 0).toFixed(2) + '</td>' +
                            '<td>$' + Number(s.tax || 0).toFixed(2) + '</td>' +
                            '<td>$' + Number(s.tip || 0).toFixed(2) + '</td>' +
                            '<td>$' + Number(s.total || 0).toFixed(2) + '</td>' +
                        '</tr>';
                    }).join('');

                    document.getElementById('reportContent').innerHTML =
                        '<div><strong>Periodo:</strong> ' + (report.from || 'Inicio') + ' a ' + (report.to || 'Hoy') + '</div>' +
                        '<div><strong>Método:</strong> ' + (report.method || 'Todos') + '</div>' +
                        '<div><strong>Sucursal:</strong> ' + (report.branch || 'Todas') + '</div>' +
                        '<div class="summary">' +
                            '<div class="metric"><div class="label">Ventas</div><div class="value">' + report.count + '</div></div>' +
                            '<div class="metric"><div class="label">Subtotal</div><div class="value">$' + report.subtotal.toFixed(2) + '</div></div>' +
                            '<div class="metric"><div class="label">IVA</div><div class="value">$' + report.tax.toFixed(2) + '</div></div>' +
                            '<div class="metric"><div class="label">Propinas</div><div class="value">$' + report.tip.toFixed(2) + '</div></div>' +
                            '<div class="metric"><div class="label">Total</div><div class="value">$' + report.total.toFixed(2) + '</div></div>' +
                            '<div class="metric"><div class="label">Efectivo</div><div class="value">$' + report.by_method.cash.toFixed(2) + '</div></div>' +
                            '<div class="metric"><div class="label">Tarjeta</div><div class="value">$' + report.by_method.card.toFixed(2) + '</div></div>' +
                            '<div class="metric"><div class="label">Transferencia</div><div class="value">$' + report.by_method.transfer.toFixed(2) + '</div></div>' +
                            '<div class="metric"><div class="label">Mixto</div><div class="value">$' + report.by_method.mixed.toFixed(2) + '</div></div>' +
                        '</div>' +
                        '<h3 style="margin:14px 0 8px">Detalle de ventas</h3>' +
                        '<table><thead><tr><th>Fecha</th><th>Sucursal</th><th>Mesa</th><th>Método</th><th>Subtotal</th><th>IVA</th><th>Propina</th><th>Total</th></tr></thead>' +
                        '<tbody>' + (rows || '<tr><td colspan="8">Sin ventas para este filtro</td></tr>') + '</tbody></table>';
                });
        }

        function exportCsv() {
            window.open('/api/sales/export.csv?' + getParams().toString(), '_blank');
        }

        function printClose() {
            fetch('/api/close-ticket?' + getParams().toString())
                .then(function(r){ return r.text(); })
                .then(function(text) {
                    var w = window.open('', '_blank');
                    w.document.write('<pre style="font-family: monospace; white-space: pre-wrap;">' + escapeHtml(text) + '</pre>');
                    w.document.close();
                    w.print();
                });
        }

        function generateProductReport() {
            var params = new URLSearchParams();
            var from = document.getElementById('prodFromDate').value;
            var to = document.getElementById('prodToDate').value;
            var groupBy = document.getElementById('prodGroupBy').value;
            var branch = document.getElementById('prodBranchFilter').value;
            if (from) params.append('from', from);
            if (to) params.append('to', to);
            if (groupBy) params.append('group_by', groupBy);
            if (branch) params.append('branch', branch);

            fetch('/api/products?' + params.toString())
                .then(function(r){ return r.json(); })
                .then(function(data) {
                    var qtys = data.products.map(function(p){ return p.qty; });
                    var maxQty = Math.max.apply(null, qtys.length ? qtys : [1]);

                    var bars = data.products.map(function(p) {
                        return '<div class="bar-row">' +
                            '<div class="bar-label" title="' + p.name + '">' + p.name + '</div>' +
                            '<div class="bar-track"><div class="bar-fill" style="width:' + (p.qty / maxQty * 100).toFixed(1) + '%"></div></div>' +
                            '<div class="bar-value">' + p.qty + ' und.</div>' +
                        '</div>';
                    }).join('');

                    var rows = data.products.map(function(p) {
                        return '<tr><td>' + p.name + '</td><td>' + p.qty + '</td><td>' + p.lines + '</td><td>$' + p.total.toFixed(2) + '</td></tr>';
                    }).join('');

                    document.getElementById('productReportContent').innerHTML =
                        '<div><strong>Periodo:</strong> ' + (from || 'Inicio') + ' a ' + (to || 'Hoy') + '</div>' +
                        '<div><strong>Agrupado por:</strong> ' + (groupBy === "category" ? "Categoría/Estación" : "Producto") + '</div>' +
                        '<h3 style="margin:14px 0 8px">Top por cantidad vendida</h3>' +
                        (bars || '<p>Sin datos para este filtro</p>') +
                        '<h3 style="margin:14px 0 8px">Detalle</h3>' +
                        '<table><thead><tr><th>Nombre</th><th>Cantidad</th><th>Líneas</th><th>Total</th></tr></thead>' +
                        '<tbody>' + (rows || '<tr><td colspan="4">Sin datos</td></tr>') + '</tbody></table>';
                });
        }

        function deltaClass(pct) {
            if (pct === null || pct === undefined) return 'flat';
            return pct > 0 ? 'up' : (pct < 0 ? 'down' : 'flat');
        }

        function deltaText(pct) {
            if (pct === null || pct === undefined) return 'sin datos previos';
            var arrow = pct > 0 ? '▲' : (pct < 0 ? '▼' : '–');
            return arrow + ' ' + Math.abs(pct) + '%';
        }

        function generateComparison() {
            var params = new URLSearchParams();
            var date = document.getElementById('compareDate').value;
            var branch = document.getElementById('compareBranchFilter').value;
            if (date) params.append('date', date);
            if (branch) params.append('branch', branch);

            fetch('/api/compare-days?' + params.toString())
                .then(function(r){ return r.json(); })
                .then(function(data) {
                    document.getElementById('compareContent').innerHTML =
                        '<div class="summary">' +
                            '<div class="metric"><div class="label">Total hoy vs ayer</div><div class="value">$' + data.today.total.toFixed(2) + '</div>' +
                                '<div class="delta ' + deltaClass(data.delta.total_pct) + '">' + deltaText(data.delta.total_pct) + '</div></div>' +
                            '<div class="metric"><div class="label">Ventas hoy vs ayer</div><div class="value">' + data.today.count + '</div>' +
                                '<div class="delta ' + deltaClass(data.delta.count_pct) + '">' + deltaText(data.delta.count_pct) + '</div></div>' +
                            '<div class="metric"><div class="label">Propinas hoy vs ayer</div><div class="value">$' + data.today.tip.toFixed(2) + '</div>' +
                                '<div class="delta ' + deltaClass(data.delta.tip_pct) + '">' + deltaText(data.delta.tip_pct) + '</div></div>' +
                        '</div>' +
                        '<div class="compare-cols">' +
                            '<div class="compare-col"><h4>' + data.today_date + ' (seleccionado)</h4>' +
                                '<div>Ventas: ' + data.today.count + '</div>' +
                                '<div>Subtotal: $' + data.today.subtotal.toFixed(2) + '</div>' +
                                '<div>IVA: $' + data.today.tax.toFixed(2) + '</div>' +
                                '<div>Propinas: $' + data.today.tip.toFixed(2) + '</div>' +
                                '<div><strong>Total: $' + data.today.total.toFixed(2) + '</strong></div></div>' +
                            '<div class="compare-col"><h4>' + data.previous_date + ' (día anterior)</h4>' +
                                '<div>Ventas: ' + data.previous.count + '</div>' +
                                '<div>Subtotal: $' + data.previous.subtotal.toFixed(2) + '</div>' +
                                '<div>IVA: $' + data.previous.tax.toFixed(2) + '</div>' +
                                '<div>Propinas: $' + data.previous.tip.toFixed(2) + '</div>' +
                                '<div><strong>Total: $' + data.previous.total.toFixed(2) + '</strong></div></div>' +
                        '</div>';
                });
        }

        function poll() {
            fetch('/api/tickets').then(function(r){ return r.json(); }).then(function(data) {
                if (data.length !== lastCount) {
                    allTickets = data;
                    lastCount = data.length;
                    renderTickets();
                    if (data.length > 0) {
                        document.title = '● Nuevo ticket — POS';
                        setTimeout(function(){ document.title = 'Simulador de Impresoras — POS'; }, 3000);
                    }
                }
            }).catch(function(){});
        }
    </script>
</body>
</html>
"""


@printer_bp.route("/")
def index():
    return render_template_string(HTML)


@printer_bp.route("/api/tickets")
def get_tickets():
    with tickets_lock:
        return jsonify(list(tickets))


@printer_bp.route("/api/clear", methods=["POST"])
def clear_tickets():
    with tickets_lock:
        tickets.clear()
    return jsonify({"ok": True})


@printer_bp.route("/api/sales")
def get_sales():
    from_date = request.args.get("from")
    to_date = request.args.get("to")
    method = request.args.get("method")
    branch = request.args.get("branch")

    filtered = sales_store.filtered(from_date, to_date, method, branch)
    summary = build_summary(filtered)

    report = {"from": from_date, "to": to_date, "method": method, "branch": branch}
    report.update(summary)
    return jsonify({"report": report, "sales": filtered})


@printer_bp.route("/api/sales/export.csv")
def export_csv():
    from_date = request.args.get("from")
    to_date = request.args.get("to")
    method = request.args.get("method")
    branch = request.args.get("branch")

    filtered = sales_store.filtered(from_date, to_date, method, branch)

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["fecha", "hora", "sucursal", "mesa", "metodo", "subtotal", "iva", "propina", "total"])
    for s in filtered:
        writer.writerow([
            s.get("date"), s.get("time"), s.get("branch"), s.get("table_code"),
            s.get("payment_method_label"), s.get("subtotal", 0), s.get("tax", 0),
            s.get("tip", 0), s.get("total", 0),
        ])

    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=ventas.csv"}
    )


@printer_bp.route("/api/close-ticket")
def close_ticket():
    from_date = request.args.get("from")
    to_date = request.args.get("to")
    method = request.args.get("method")
    branch = request.args.get("branch")

    filtered = sales_store.filtered(from_date, to_date, method, branch)
    summary = build_summary(filtered)
    by_method = summary["by_method"]

    lines = []
    lines.append("=" * 40)
    lines.append("{:^40}".format("CIERRE DE CAJA"))
    lines.append("=" * 40)
    lines.append("Periodo: {} -> {}".format(from_date or "Inicio", to_date or "Hoy"))
    lines.append("Método: {}".format(method or "Todos"))
    lines.append("Sucursal: {}".format(branch or "Todas"))
    lines.append("-" * 40)
    lines.append("Ventas: {}".format(summary["count"]))
    lines.append("Subtotal: ${:.2f}".format(summary["subtotal"]))
    lines.append("IVA: ${:.2f}".format(summary["tax"]))
    lines.append("Propinas: ${:.2f}".format(summary["tip"]))
    lines.append("TOTAL: ${:.2f}".format(summary["total"]))
    lines.append("-" * 40)
    lines.append("Por método de pago:")
    lines.append("Efectivo: ${:.2f}".format(by_method["cash"]))
    lines.append("Tarjeta: ${:.2f}".format(by_method["card"]))
    lines.append("Transferencia: ${:.2f}".format(by_method["transfer"]))
    lines.append("Mixto: ${:.2f}".format(by_method["mixed"]))
    lines.append("=" * 40)
    return "\n".join(lines)


@printer_bp.route("/api/clear-sales", methods=["POST"])
def clear_sales():
    sales_store.clear()
    return jsonify({"ok": True})


@printer_bp.route("/api/products")
def get_products():
    from_date = request.args.get("from")
    to_date = request.args.get("to")
    branch = request.args.get("branch")
    group_by = request.args.get("group_by", "name")
    if group_by not in ("name", "category"):
        group_by = "name"

    filtered = sales_store.filtered(from_date, to_date, None, branch)
    products = build_product_report(filtered, group_by=group_by)

    return jsonify({
        "from": from_date,
        "to": to_date,
        "branch": branch,
        "group_by": group_by,
        "products": products,
    })


@printer_bp.route("/api/compare-days")
def compare_days():
    target_date = request.args.get("date")
    branch = request.args.get("branch")
    result = build_day_comparison(target_date, branch)
    return jsonify(result)


def add_ticket_from_payload(payload_data, station, *, raw_size=None, from_ip=None, ticket_type=None, text_content=None):
    if payload_data is None:
        payload_data = {}

    if ticket_type is None:
        ticket_type = payload_data.get("type", station) if isinstance(payload_data, dict) else station

    if text_content is None:
        if isinstance(payload_data, dict):
            text_content = format_ticket_from_payload(payload_data, station)
        else:
            text_content = str(payload_data)

    ui_type = ticket_type if ticket_type in (
        "kitchen", "refill", "cashier", "cashier_bill", "payment_receipt"
    ) else station

    ticket = {
        "id": len(tickets) + 1,
        "station": station,
        "ticket_type": ui_type,
        "timestamp": datetime.now().strftime("%H:%M:%S"),
        "date": datetime.now().strftime("%d/%m/%Y"),
        "content": text_content,
        "raw_size": raw_size or 0,
        "from_ip": from_ip,
    }

    with tickets_lock:
        tickets.insert(0, ticket)
        if len(tickets) > 50:
            tickets.pop()

    if isinstance(payload_data, dict) and should_store_sale(payload_data, ui_type):
        sale = normalize_sale(payload_data, station)
        add_sale(sale)

    print("[{}] Ticket desde {} — {} bytes".format(ui_type.upper(), from_ip or "local", ticket["raw_size"]))
    return ticket


def handle_connection(conn, addr, station):
    with conn:
        chunks = []
        while True:
            chunk = conn.recv(4096)
            if not chunk:
                break
            chunks.append(chunk)

        raw = b"".join(chunks)
        if not raw:
            return

        payload_data = None
        try:
            payload_data = json.loads(raw.decode("utf-8"))
            ticket_type = payload_data.get("type", station)
            text_content = format_ticket_from_payload(payload_data, station)
        except Exception:
            ticket_type = station
            text_content = parse_escpos(raw)

        add_ticket_from_payload(
            payload_data,
            station,
            raw_size=len(raw),
            from_ip=addr[0],
            ticket_type=ticket_type,
            text_content=text_content,
        )


servers_started = False
servers_lock = threading.Lock()

def tcp_server(port, station):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind(("0.0.0.0", port))
        s.listen(5)
        print("[{}] Escuchando en puerto {}...".format(station.upper(), port))
        while True:
            conn, addr = s.accept()
            threading.Thread(target=handle_connection, args=(conn, addr, station), daemon=True).start()


def start_printer_simulator():
    global servers_started
    with servers_lock:
        if servers_started:
            return

        threading.Thread(target=tcp_server, args=(KITCHEN_PORT, "kitchen"), daemon=True).start()
        threading.Thread(target=tcp_server, args=(CASHIER_PORT, "cashier"), daemon=True).start()
        print("\n" + "=" * 50)
        print("  SIMULADOR DE IMPRESORAS POS")
        print("=" * 50)
        print("  Cocina      -> TCP  127.0.0.0:{}".format(KITCHEN_PORT))
        print("  Caja        -> TCP  127.0.0.1:{}".format(CASHIER_PORT))
        print("  Web UI      -> https://<your-service>/")
        print("=" * 50 + "\n")


def init_printer_simulator(app):
    app.register_blueprint(printer_bp)
    start_printer_simulator()
