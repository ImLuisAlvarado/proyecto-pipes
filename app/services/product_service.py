# app/services/product_service.py
from uuid import uuid4
from app.models.product import Product
from app.repositories.product_repository import ProductRepository

class ProductService:
    def __init__(self):
        self.repo = ProductRepository()

    def get_all_products(self, branch_id=None):
        return self.repo.get_all(branch_id)

    def get_product_by_id(self, product_id):
        product = self.repo.get_by_id(product_id)
        if not product:
            raise ValueError("Producto no encontrado")
        return product

    def create_product(self, schema):
        product = Product(
            id=uuid4(),
            branch_id=schema.branch_id,
            category_id=schema.category_id,
            name=schema.name,
            description=schema.description,
            price=schema.price,
            tax_rate=schema.tax_rate,
            print_station=schema.print_station,
            active=schema.active
        )
        return self.repo.create(product)

    def update_product(self, product_id, schema):
        product = self.get_product_by_id(product_id)
        data = schema.model_dump(exclude_unset=True)
        for key, value in data.items():
            setattr(product, key, value)
        return self.repo.update(product)