# app/repositories/product_repository.py
from app.models.product import Product as ProductModel
from app.extensions import db

class ProductRepository:
    def get_all(self, branch_id=None):
        query = ProductModel.query
        if branch_id:
            query = query.filter_by(branch_id=branch_id)
        return query.order_by(ProductModel.name.asc()).all()

    def get_by_id(self, product_id):
        return ProductModel.query.get(product_id)

    def create(self, product):
        db.session.add(product)
        db.session.commit()
        return product

    def update(self, product):
        db.session.commit()
        return product