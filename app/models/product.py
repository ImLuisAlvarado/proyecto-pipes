# app/models/product.py
from datetime import datetime
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy import text
from app.extensions import db


class Product(db.Model):
    __tablename__ = 'products'

    id            = db.Column(UUID(as_uuid=True), primary_key=True,
                              server_default=text("gen_random_uuid()"))
    branch_id     = db.Column(UUID(as_uuid=True),
                              db.ForeignKey('branches.id', ondelete='CASCADE'),
                              nullable=False)
    category_id   = db.Column(UUID(as_uuid=True),
                              db.ForeignKey('categories.id', ondelete='SET NULL'),
                              nullable=True)
    name          = db.Column(db.String(120), nullable=False)
    description   = db.Column(db.Text, nullable=True)
    price         = db.Column(db.Numeric(12, 2), nullable=False)
    tax_rate      = db.Column(db.Numeric(5, 2), nullable=False,
                              server_default=text("0"))
    print_station = db.Column(db.String(40), nullable=False,
                              server_default=text("'kitchen'"))
    active        = db.Column(db.Boolean, nullable=False,
                              server_default=text("true"))
    created_at    = db.Column(db.DateTime(timezone=True), nullable=False,
                              default=datetime.utcnow)
    updated_at    = db.Column(db.DateTime(timezone=True), nullable=False,
                              default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        db.UniqueConstraint('branch_id', 'name', name='uq_products_branch_name'),
        db.CheckConstraint('price >= 0', name='products_price_check'),
        db.CheckConstraint('tax_rate >= 0', name='products_tax_rate_check'),
    )

    def to_dict(self):
        return {
            'id':            str(self.id),
            'branch_id':     str(self.branch_id),
            'category_id':   str(self.category_id) if self.category_id else None,
            'name':          self.name,
            'description':   self.description,
            'price':         float(self.price),
            'tax_rate':      float(self.tax_rate),
            'print_station': self.print_station,
            'active':        self.active,
        }