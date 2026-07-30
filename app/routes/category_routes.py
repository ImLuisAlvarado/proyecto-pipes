# app/routes/category_routes.py
from flask import Blueprint, request, jsonify
from uuid import UUID
from pydantic import ValidationError

from app.services.category_service import CategoryService
from app.schemas.category import CategoryCreate, CategoryUpdate, CategoryResponse

category_bp = Blueprint('categories', __name__, url_prefix='/api/v1/categories')
category_service = CategoryService()


def _val_err(e):
    return jsonify({"error": "Error de validación", "details": e.errors(include_url=False)}), 422


@category_bp.route('', methods=['GET'])
def list_categories():
    """Lista categorías. Filtra por branch_id si se pasa como query param."""
    branch_id = request.args.get('branch_id')
    categories = category_service.get_all(branch_id=branch_id)
    return jsonify([CategoryResponse.model_validate(c).model_dump() for c in categories]), 200


@category_bp.route('/<uuid:category_id>', methods=['GET'])
def get_category(category_id: UUID):
    category = category_service.get_by_id(category_id)
    return jsonify(CategoryResponse.model_validate(category).model_dump()), 200


@category_bp.route('', methods=['POST'])
def create_category():
    json_data = request.get_json()
    if not json_data:
        return jsonify({"error": "Cuerpo vacío"}), 400
    try:
        schema  = CategoryCreate(**json_data)
        created = category_service.create(schema)
        return jsonify(CategoryResponse.model_validate(created).model_dump()), 201
    except ValidationError as e:
        return _val_err(e)


@category_bp.route('/<uuid:category_id>', methods=['PATCH'])
def update_category(category_id: UUID):
    json_data = request.get_json()
    if not json_data:
        return jsonify({"error": "Cuerpo vacío"}), 400
    try:
        schema  = CategoryUpdate(**json_data)
        updated = category_service.update(category_id, schema)
        return jsonify(CategoryResponse.model_validate(updated).model_dump()), 200
    except ValidationError as e:
        return _val_err(e)