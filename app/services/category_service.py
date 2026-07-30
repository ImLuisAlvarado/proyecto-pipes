# app/services/category_service.py
from uuid import UUID
from flask import abort
from app.extensions import db
from app.models.core import Category
from app.schemas.category import CategoryCreate, CategoryUpdate


class CategoryService:

    def get_all(self, branch_id=None) -> list[Category]:
        q = Category.query.filter_by(active=True)
        if branch_id:
            q = q.filter_by(branch_id=branch_id)
        return q.order_by(Category.sort_order.asc(), Category.name.asc()).all()

    def get_by_id(self, category_id: UUID) -> Category:
        category = Category.query.get(category_id)
        if not category:
            abort(404, description="Categoría no encontrada.")
        return category

    def create(self, schema: CategoryCreate) -> Category:
        category = Category(
            branch_id=schema.branch_id,
            name=schema.name,
            sort_order=schema.sort_order,
            active=schema.active,
        )
        db.session.add(category)
        db.session.commit()
        return category

    def update(self, category_id: UUID, schema: CategoryUpdate) -> Category:
        category = self.get_by_id(category_id)
        for key, value in schema.model_dump(exclude_unset=True).items():
            setattr(category, key, value)
        db.session.commit()
        return category