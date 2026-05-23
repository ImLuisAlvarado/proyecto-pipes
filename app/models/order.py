from datetime import datetime
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy import Enum, CheckConstraint
from app.extensions import db

order_status_enum = Enum(
    'open', 'sent', 'in_preparation', 'ready', 'closed', 'cancelled',
    name='order_status'
)

sync_status_enum = Enum(
    'pending', 'synced', 'failed',
    name='sync_status'
)


class Order(db.Model):
    __tablename__ = 'orders'

    id = db.Column(UUID(as_uuid=True), primary_key=True, server_default=db.text("gen_random_uuid()"))
    branch_id = db.Column(UUID(as_uuid=True), db.ForeignKey('branches.id', ondelete='CASCADE'), nullable=False)
    table_id = db.Column(UUID(as_uuid=True), db.ForeignKey('dining_tables.id', ondelete='RESTRICT'), nullable=False)
    customer_id = db.Column(UUID(as_uuid=True), db.ForeignKey('customers.id', ondelete='SET NULL'), nullable=True)
    opened_by = db.Column(UUID(as_uuid=True), db.ForeignKey('users.id', ondelete='RESTRICT'), nullable=False)
    closed_by = db.Column(UUID(as_uuid=True), db.ForeignKey('users.id', ondelete='RESTRICT'), nullable=True)
    
    status = db.Column(order_status_enum, nullable=False, server_default='open')
    subtotal = db.Column(db.Numeric(12, 2), nullable=False, default=0.00)
    tax_total = db.Column(db.Numeric(12, 2), nullable=False, default=0.00)
    discount_total = db.Column(db.Numeric(12, 2), nullable=False, default=0.00)
    total = db.Column(db.Numeric(12, 2), nullable=False, default=0.00)
    notes = db.Column(db.Text, nullable=True)
    
    opened_at = db.Column(db.DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    closed_at = db.Column(db.DateTime(timezone=True), nullable=True)
    offline_uuid = db.Column(UUID(as_uuid=True), nullable=False, server_default=db.text("gen_random_uuid()"))
    sync_status = db.Column(sync_status_enum, nullable=False, server_default='pending')
    synced_at = db.Column(db.DateTime(timezone=True), nullable=True)

    # Relaciones estables de SQLAlchemy
    refills = db.relationship('OrderRefill', backref='order', lazy=True, cascade="all, delete-orphan")
    items = db.relationship('OrderItem', backref='order', lazy=True, cascade="all, delete-orphan")


class OrderRefill(db.Model):
    __tablename__ = 'order_refills'

    id = db.Column(UUID(as_uuid=True), primary_key=True, server_default=db.text("gen_random_uuid()"))
    order_id = db.Column(UUID(as_uuid=True), db.ForeignKey('orders.id', ondelete='CASCADE'), nullable=False)
    created_by = db.Column(UUID(as_uuid=True), db.ForeignKey('users.id', ondelete='RESTRICT'), nullable=False)
    reason = db.Column(db.Text, nullable=True)
    refill_no = db.Column(db.Integer, nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=datetime.utcnow)

    # Relación inversa hacia los items que se agrupan en esta ronda de refills
    items = db.relationship('OrderItem', backref='refill', lazy=True)


class OrderItem(db.Model):
    __tablename__ = 'order_items'

    id = db.Column(UUID(as_uuid=True), primary_key=True, server_default=db.text("gen_random_uuid()"))
    order_id = db.Column(UUID(as_uuid=True), db.ForeignKey('orders.id', ondelete='CASCADE'), nullable=False)
    refill_id = db.Column(UUID(as_uuid=True), db.ForeignKey('order_refills.id', ondelete='SET NULL'), nullable=True)
    product_id = db.Column(UUID(as_uuid=True), db.ForeignKey('products.id', ondelete='RESTRICT'), nullable=False)
    
    qty = db.Column(db.Numeric(12, 2), nullable=False)
    unit_price = db.Column(db.Numeric(12, 2), nullable=False)
    tax_rate = db.Column(db.Numeric(5, 2), nullable=False, default=0.00)
    notes = db.Column(db.Text, nullable=True)
    station = db.Column(db.String(40), nullable=False)
    is_refill = db.Column(db.Boolean, nullable=False, default=False)
    printed_at = db.Column(db.DateTime(timezone=True), nullable=True)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=datetime.utcnow)

    seat_number = db.Column(db.Integer, nullable=False, default=1)

    # Restricciones Check de base de datos para asegurar integridad matemática
    __table_args__ = (
        CheckConstraint('qty > 0', name='order_items_qty_check'),
        CheckConstraint('unit_price >= 0', name='order_items_unit_price_check'),
    )