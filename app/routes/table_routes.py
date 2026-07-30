# app/routes/table_routes.py
from flask import Blueprint, request, jsonify
from uuid import UUID
from pydantic import ValidationError

from app.schemas.table import TableCreate, TableUpdate, TableResponse
from app.services.table_service import TableService

table_bp = Blueprint('tables', __name__, url_prefix='/api/v1/tables')
table_service = TableService()


def _val_err(e):
    return jsonify({"error": "Error de validación", "details": e.errors(include_url=False)}), 422


@table_bp.route('', methods=['GET'])
def get_tables():
    branch_id = request.args.get('branch_id')
    tables = table_service.get_all_tables(branch_id)
    return jsonify([TableResponse.model_validate(t).model_dump() for t in tables]), 200


@table_bp.route('/<uuid:table_id>', methods=['GET'])
def get_table(table_id: UUID):
    table = table_service.get_table_by_id(table_id)
    return jsonify(TableResponse.model_validate(table).model_dump()), 200


@table_bp.route('', methods=['POST'])
def create_table():
    json_data = request.get_json()
    if not json_data:
        return jsonify({"error": "Cuerpo vacío"}), 400
    try:
        schema  = TableCreate(**json_data)
        created = table_service.create_table(schema)
        return jsonify(TableResponse.model_validate(created).model_dump()), 201
    except ValidationError as e:
        return _val_err(e)


@table_bp.route('/<uuid:table_id>', methods=['PATCH'])
def update_table(table_id: UUID):
    json_data = request.get_json()
    if not json_data:
        return jsonify({"error": "Cuerpo vacío"}), 400
    try:
        schema  = TableUpdate(**json_data)
        updated = table_service.update_table(table_id, schema)
        return jsonify(TableResponse.model_validate(updated).model_dump()), 200
    except ValidationError as e:
        return _val_err(e)


# ── POST /api/v1/tables/<id>/open ────────────────────────────────────────
@table_bp.route('/<uuid:table_id>/open', methods=['POST'])
def open_table(table_id: UUID):
    """
    Abre una mesa: cambia status a 'occupied' y crea una orden vacía.
    Body esperado: { "branch_id": "...", "opened_by": "..." }
    Retorna el OrderDTO que Android espera.
    """
    from app.schemas.order import OrderCreate, OrderResponse
    from app.services.order_service import OrderService

    json_data = request.get_json() or {}
    branch_id  = json_data.get('branch_id')
    opened_by  = json_data.get('opened_by')

    if not branch_id or not opened_by:
        return jsonify({"error": "Se requieren branch_id y opened_by"}), 400

    # 1. Marcar mesa como ocupada
    table_service.update_table(table_id, TableUpdate(status='occupied'))

    # 2. Crear la orden vacía asociada a esta mesa
    order_schema = OrderCreate(
        branch_id=branch_id,
        table_id=str(table_id),
        opened_by=opened_by,
    )
    order = OrderService().create_new_order(order_schema)
    return jsonify(OrderResponse.model_validate(order).model_dump()), 201


# ── POST /api/v1/tables/<id>/close ───────────────────────────────────────
@table_bp.route('/<uuid:table_id>/close', methods=['POST'])
def close_table(table_id: UUID):
    """
    Cierra la mesa: cambia status a 'available'.
    Retorna la orden cerrada si se manda order_id en el body.
    """
    from app.schemas.order import OrderResponse
    from app.services.order_service import OrderService

    json_data  = request.get_json() or {}
    order_id   = json_data.get('order_id')
    closed_by  = json_data.get('closed_by')

    # Liberar la mesa
    table_service.update_table(table_id, TableUpdate(status='available'))

    if order_id:
        order = OrderService().close_account(order_id, closed_by)
        return jsonify(OrderResponse.model_validate(order).model_dump()), 200

    return jsonify({"status": "ok", "message": "Mesa liberada"}), 200