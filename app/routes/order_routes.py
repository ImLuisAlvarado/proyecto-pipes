from flask import Blueprint, request, jsonify
from uuid import UUID
from pydantic import ValidationError

from app.services.order_service import OrderService
from app.schemas.order import OrderCreate, OrderRefillCreate, OrderResponse, OrderClose

# Definimos el Blueprint para agrupar los endpoints de órdenes
order_bp = Blueprint('orders', __name__, url_prefix='/api/v1/orders')
order_service = OrderService()


@order_bp.route('', methods=['POST'])
def create_order():
    """Abre una nueva comanda en una mesa con o sin items iniciales."""
    json_data = request.get_json()
    if not json_data:
        return jsonify({"error": "El cuerpo de la petición no puede estar vacío"}), 400

    try:
        # Pydantic v2 valida la estructura del JSON entrante
        order_schema = OrderCreate(**json_data)
        
        # Pasamos el objeto validado a la capa de negocio
        new_order = order_service.create_new_order(order_schema)
        
        # Transformamos el modelo de SQLAlchemy al esquema de respuesta JSON
        response_data = OrderResponse.model_validate(new_order)
        return jsonify(response_data.model_dump()), 201

    except ValidationError as e:
        # Si Pydantic encuentra errores (ej: UUID inválido o cantidad <= 0), responde automáticamente
        return jsonify({"error": "Error de validación", "details": e.errors(include_url=False)}), 422


@order_bp.route('/<uuid:order_id>', methods=['GET'])
def get_order(order_id: UUID):
    """Obtiene el estado actual y cuenta detallada de una orden por su UUID."""
    order = order_service.get_order_by_id(order_id)
    response_data = OrderResponse.model_validate(order)
    return jsonify(response_data.model_dump()), 200


@order_bp.route('/<uuid:order_id>/refills', methods=['POST'])
def add_refill(order_id: UUID):
    """Registra una nueva ronda de refills (bebidas/extras) a una orden abierta."""
    json_data = request.get_json()
    if not json_data:
        return jsonify({"error": "El cuerpo de la petición no puede estar vacío"}), 400

    try:
        # Validamos los datos de la ronda de refill
        refill_schema = OrderRefillCreate(**json_data)
        
        # Procesamos la lógica de negocio y recalculamos los totales
        updated_order = order_service.request_order_refill(order_id, refill_schema)
        
        response_data = OrderResponse.model_validate(updated_order)
        return jsonify(response_data.model_dump()), 200

    except ValidationError as e:
        return jsonify({"error": "Error de validación", "details": e.errors(include_url=False)}), 422
    
@order_bp.route('/<uuid:order_id>/close', methods=['PATCH'])
def close_order(order_id: UUID):
    """Cierra la orden una vez que ha sido pagada."""
    json_data = request.get_json()
    if not json_data:
        return jsonify({"error": "El cuerpo de la petición no puede estar vacío"}), 400

    try:
        close_schema = OrderClose(**json_data)
        closed_order = order_service.close_account(order_id, close_schema.closed_by)
        
        response_data = OrderResponse.model_validate(closed_order)
        return jsonify(response_data.model_dump()), 200

    except ValidationError as e:
        return jsonify({"error": "Error de validación", "details": e.errors(include_url=False)}), 422    