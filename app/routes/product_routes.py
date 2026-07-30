from flask import Blueprint, request, jsonify
from uuid import UUID
from pydantic import ValidationError

from app.schemas.product import ProductCreate, ProductUpdate, ProductResponse
from app.services.product_service import ProductService

product_bp = Blueprint('products', __name__, url_prefix='/api/v1/products')
product_service = ProductService()

@product_bp.route('', methods=['GET'])
def get_products():
    branch_id = request.args.get('branch_id')
    products = product_service.get_all_products(branch_id)
    return jsonify([ProductResponse.model_validate(p).model_dump() for p in products]), 200

@product_bp.route('/<uuid:product_id>', methods=['GET'])
def get_product(product_id: UUID):
    product = product_service.get_product_by_id(product_id)
    return jsonify(ProductResponse.model_validate(product).model_dump()), 200

@product_bp.route('', methods=['POST'])
def create_product():
    json_data = request.get_json()
    if not json_data:
        return jsonify({"error": "El cuerpo de la petición no puede estar vacío"}), 400
    try:
        schema = ProductCreate(**json_data)
        created = product_service.create_product(schema)
        return jsonify(ProductResponse.model_validate(created).model_dump()), 201
    except ValidationError as e:
        return jsonify({"error": "Error de validación", "details": e.errors(include_url=False)}), 422

@product_bp.route('/<uuid:product_id>', methods=['PATCH'])
def update_product(product_id: UUID):
    json_data = request.get_json()
    if not json_data:
        return jsonify({"error": "El cuerpo de la petición no puede estar vacío"}), 400
    try:
        schema = ProductUpdate(**json_data)
        updated = product_service.update_product(product_id, schema)
        return jsonify(ProductResponse.model_validate(updated).model_dump()), 200
    except ValidationError as e:
        return jsonify({"error": "Error de validación", "details": e.errors(include_url=False)}), 422