# app/routes/order_routes.py
from flask import Blueprint, request, jsonify
from uuid import UUID
from pydantic import ValidationError

from app.services.order_service import OrderService
from app.schemas.bill import BillResponse
from app.schemas.order import (
    OrderCreate, OrderRefillCreate, OrderResponse, OrderClose, OrderItemCreate
)

order_bp = Blueprint('orders', __name__, url_prefix='/api/v1/orders')
order_service = OrderService()


def _val_err(e: ValidationError):
    return jsonify({"error": "Error de validación", "details": e.errors(include_url=False)}), 422


# ── GET /api/v1/orders ────────────────────────────────────────────────────
@order_bp.route('', methods=['GET'])
def list_orders():
    """Lista órdenes. Filtra por branch_id y/o status si se pasan como query params."""
    branch_id = request.args.get('branch_id')
    status    = request.args.get('status')
    orders    = order_service.list_orders(branch_id=branch_id, status=status)
    return jsonify([OrderResponse.model_validate(o).model_dump() for o in orders]), 200


# ── POST /api/v1/orders ───────────────────────────────────────────────────
@order_bp.route('', methods=['POST'])
def create_order():
    json_data = request.get_json()
    if not json_data:
        return jsonify({"error": "Cuerpo vacío"}), 400
    try:
        schema    = OrderCreate(**json_data)
        new_order = order_service.create_new_order(schema)
        return jsonify(OrderResponse.model_validate(new_order).model_dump()), 201
    except ValidationError as e:
        return _val_err(e)


# ── GET /api/v1/orders/<id> ───────────────────────────────────────────────
@order_bp.route('/<uuid:order_id>', methods=['GET'])
def get_order(order_id: UUID):
    order = order_service.get_order_by_id(order_id)
    return jsonify(OrderResponse.model_validate(order).model_dump()), 200


# ── PATCH /api/v1/orders/<id> ────────────────────────────────────────────
@order_bp.route('/<uuid:order_id>', methods=['PATCH'])
def update_order(order_id: UUID):
    """Actualización parcial de campos de la orden (notas, customer_id, etc.)."""
    json_data = request.get_json() or {}
    updated   = order_service.update_order(order_id, json_data)
    return jsonify(OrderResponse.model_validate(updated).model_dump()), 200

@order_bp.route('/<uuid:order_id>/items/<uuid:item_id>', methods=['PATCH'])
def update_order_item(order_id: UUID, item_id: UUID):
    json_data = request.get_json() or {}
    updated = order_service.update_order_item(order_id, item_id, json_data)
    return jsonify(OrderResponse.model_validate(updated).model_dump()), 200


# ── POST /api/v1/orders/<id>/items ───────────────────────────────────────
@order_bp.route('/<uuid:order_id>/items', methods=['POST'])
def add_items(order_id: UUID):
    json_data = request.get_json()
    if not json_data:
        return jsonify({"error": "Cuerpo vacío"}), 400
    try:
        # Acepta {"items": [...]} o directamente [...]
        raw = json_data.get('items', json_data) if isinstance(json_data, dict) else json_data
        if not isinstance(raw, list):
            raw = [raw]
        schemas = [OrderItemCreate(**i) for i in raw]
        updated = order_service.add_items_to_order(order_id, schemas)
        return jsonify(OrderResponse.model_validate(updated).model_dump()), 200
    except ValidationError as e:
        return _val_err(e)
    

@order_bp.route('/<uuid:order_id>/items/<uuid:item_id>', methods=['DELETE'])
def delete_order_item(order_id: UUID, item_id: UUID):
    updated = order_service.delete_order_item(order_id, item_id)
    return jsonify(OrderResponse.model_validate(updated).model_dump()), 200


# ── POST /api/v1/orders/<id>/send-kitchen ────────────────────────────────
@order_bp.route('/<uuid:order_id>/send-kitchen', methods=['POST'])
def send_to_kitchen(order_id: UUID):
    updated = order_service.send_to_kitchen(order_id)
    return jsonify(OrderResponse.model_validate(updated).model_dump()), 200


@order_bp.route('/<uuid:order_id>/print-bill', methods=['POST'])
def print_bill(order_id: UUID):
    try:
        bill = order_service.print_bill(order_id)
        return jsonify(BillResponse.model_validate(bill).model_dump()), 200
    except ValidationError as e:
        return _val_err(e)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ── POST /api/v1/orders/<id>/refills ─────────────────────────────────────
@order_bp.route('/<uuid:order_id>/refills', methods=['POST'])
def add_refill(order_id: UUID):
    json_data = request.get_json()
    if not json_data:
        return jsonify({"error": "Cuerpo vacío"}), 400
    try:
        schema  = OrderRefillCreate(**json_data)
        updated = order_service.request_order_refill(order_id, schema)
        return jsonify(OrderResponse.model_validate(updated).model_dump()), 200
    except ValidationError as e:
        return _val_err(e)


# ── GET /api/v1/orders/<id>/refills ──────────────────────────────────────
@order_bp.route('/<uuid:order_id>/refills', methods=['GET'])
def get_refills(order_id: UUID):
    from app.schemas.order import OrderRefillResponse
    refills = order_service.get_refills(order_id)
    return jsonify([OrderRefillResponse.model_validate(r).model_dump() for r in refills]), 200


# ── POST /api/v1/orders/<id>/payments ────────────────────────────────────
@order_bp.route('/<uuid:order_id>/payments', methods=['POST'])
def create_payment(order_id: UUID):
    from app.schemas.payment import PaymentCreate, PaymentResponse
    from app.services.payment_service import PaymentService
    json_data = request.get_json()
    if not json_data:
        return jsonify({"error": "Cuerpo vacío"}), 400
    try:
        schema  = PaymentCreate(**json_data)
        payment = PaymentService().create_payment(order_id, schema)
        return jsonify(PaymentResponse.model_validate(payment).model_dump()), 201
    except ValidationError as e:
        return _val_err(e)


# ── GET /api/v1/orders/<id>/payments ─────────────────────────────────────
@order_bp.route('/<uuid:order_id>/payments', methods=['GET'])
def get_payments(order_id: UUID):
    from app.schemas.payment import PaymentResponse
    from app.services.payment_service import PaymentService
    payments = PaymentService().get_payments_by_order(order_id)
    return jsonify([PaymentResponse.model_validate(p).model_dump() for p in payments]), 200


# ── PATCH /api/v1/orders/<id>/transfer ───────────────────────────────────
@order_bp.route('/<uuid:order_id>/transfer', methods=['PATCH'])
def transfer_order(order_id: UUID):
    """Mueve una orden a otra mesa liberando la origen y ocupando la destino."""
    json_data = request.get_json()
    if not json_data:
        return jsonify({"error": "Cuerpo vacío"}), 400
    try:
        from app.schemas.order import OrderTransfer
        schema  = OrderTransfer(**json_data)
        updated = order_service.transfer_order(order_id, schema.new_table_id)
        return jsonify(OrderResponse.model_validate(updated).model_dump()), 200
    except ValidationError as e:
        return _val_err(e)


# ── PATCH /api/v1/orders/<id>/close ──────────────────────────────────────
@order_bp.route('/<uuid:order_id>/close', methods=['PATCH'])
def close_order(order_id: UUID):
    json_data = request.get_json() or {}
    try:
        schema = OrderClose(**json_data)
        closed = order_service.close_account(
            order_id,
            schema.closed_by,
            schema.payment_method or 'N/A'
        )
        return jsonify(OrderResponse.model_validate(closed).model_dump()), 200
    except ValidationError as e:
        return _val_err(e)