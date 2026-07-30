# app/models/order.py
from datetime import datetime
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy import Enum, CheckConstraint, text
from app.extensions import db


order_status_enum = Enum(
    'open', 'sent', 'in_preparation', 'ready', 'closed', 'cancelled',
    name='order_status'
)

sync_status_enum = Enum(
    'pending', 'synced', 'failed',
    name='sync_status'
)


# ---------------------------------------------------------------------------
# Order
# ---------------------------------------------------------------------------

class Order(db.Model):
    __tablename__ = 'orders'

    id             = db.Column(UUID(as_uuid=True), primary_key=True,
                               server_default=text("gen_random_uuid()"))
    branch_id      = db.Column(UUID(as_uuid=True),
                               db.ForeignKey('branches.id', ondelete='CASCADE'),
                               nullable=False)
    table_id       = db.Column(UUID(as_uuid=True),
                               db.ForeignKey('dining_tables.id', ondelete='RESTRICT'),
                               nullable=False)
    customer_id    = db.Column(UUID(as_uuid=True),
                               db.ForeignKey('customers.id', ondelete='SET NULL'),
                               nullable=True)
    opened_by      = db.Column(UUID(as_uuid=True),
                               db.ForeignKey('users.id', ondelete='RESTRICT'),
                               nullable=False)
    closed_by      = db.Column(UUID(as_uuid=True),
                               db.ForeignKey('users.id', ondelete='RESTRICT'),
                               nullable=True)

    status         = db.Column(order_status_enum, nullable=False,
                               server_default='open')
    subtotal       = db.Column(db.Numeric(12, 2), nullable=False, default=0.00)
    tax_total      = db.Column(db.Numeric(12, 2), nullable=False, default=0.00)
    discount_total = db.Column(db.Numeric(12, 2), nullable=False, default=0.00)
    total          = db.Column(db.Numeric(12, 2), nullable=False, default=0.00)
    notes          = db.Column(db.Text, nullable=True)

    opened_at      = db.Column(db.DateTime(timezone=True), nullable=False,
                               default=datetime.utcnow)
    closed_at      = db.Column(db.DateTime(timezone=True), nullable=True)

    # Soporte offline / sincronización con app Android
    offline_uuid   = db.Column(UUID(as_uuid=True), nullable=False,
                               server_default=text("gen_random_uuid()"))
    sync_status    = db.Column(sync_status_enum, nullable=False,
                               server_default='pending')
    synced_at      = db.Column(db.DateTime(timezone=True), nullable=True)

    __table_args__ = (
        db.UniqueConstraint('branch_id', 'offline_uuid',
                            name='uq_orders_branch_offline_uuid'),
    )

    # Relaciones
    refills  = db.relationship('OrderRefill', backref='order', lazy=True,
                               cascade='all, delete-orphan')
    items    = db.relationship('OrderItem', backref='order', lazy=True,
                               cascade='all, delete-orphan')
    payments = db.relationship('Payment', backref='order', lazy=True,
                               cascade='all, delete-orphan')

    def to_dict(self, include_items=False):
        data = {
            'id':             str(self.id),
            'branch_id':      str(self.branch_id),
            'table_id':       str(self.table_id),
            'customer_id':    str(self.customer_id) if self.customer_id else None,
            'opened_by':      str(self.opened_by),
            'closed_by':      str(self.closed_by) if self.closed_by else None,
            'status':         self.status,
            'subtotal':       float(self.subtotal),
            'tax_total':      float(self.tax_total),
            'discount_total': float(self.discount_total),
            'total':          float(self.total),
            'notes':          self.notes,
            'opened_at':      self.opened_at.isoformat() if self.opened_at else None,
            'closed_at':      self.closed_at.isoformat() if self.closed_at else None,
            'offline_uuid':   str(self.offline_uuid),
            'sync_status':    self.sync_status,
            'synced_at':      self.synced_at.isoformat() if self.synced_at else None,
        }
        if include_items:
            data['items'] = [i.to_dict() for i in self.items]
        return data


# ---------------------------------------------------------------------------
# OrderRefill
# ---------------------------------------------------------------------------

class OrderRefill(db.Model):
    __tablename__ = 'order_refills'

    id         = db.Column(UUID(as_uuid=True), primary_key=True,
                           server_default=text("gen_random_uuid()"))
    order_id   = db.Column(UUID(as_uuid=True),
                           db.ForeignKey('orders.id', ondelete='CASCADE'),
                           nullable=False)
    created_by = db.Column(UUID(as_uuid=True),
                           db.ForeignKey('users.id', ondelete='RESTRICT'),
                           nullable=False)
    reason     = db.Column(db.Text, nullable=True)
    refill_no  = db.Column(db.Integer, nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False,
                           default=datetime.utcnow)

    __table_args__ = (
        db.UniqueConstraint('order_id', 'refill_no',
                            name='uq_order_refills_order_refill_no'),
    )

    # Relación inversa — ítems agrupados en esta ronda
    items = db.relationship('OrderItem', backref='refill', lazy=True)

    def to_dict(self):
        return {
            'id':         str(self.id),
            'order_id':   str(self.order_id),
            'created_by': str(self.created_by),
            'reason':     self.reason,
            'refill_no':  self.refill_no,
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }


# ---------------------------------------------------------------------------
# OrderItem
# ---------------------------------------------------------------------------

class OrderItem(db.Model):
    __tablename__ = 'order_items'

    id         = db.Column(UUID(as_uuid=True), primary_key=True,
                           server_default=text("gen_random_uuid()"))
    order_id   = db.Column(UUID(as_uuid=True),
                           db.ForeignKey('orders.id', ondelete='CASCADE'),
                           nullable=False)
    refill_id  = db.Column(UUID(as_uuid=True),
                           db.ForeignKey('order_refills.id', ondelete='SET NULL'),
                           nullable=True)
    product_id = db.Column(UUID(as_uuid=True),
                           db.ForeignKey('products.id', ondelete='RESTRICT'),
                           nullable=False)

    qty        = db.Column(db.Numeric(12, 2), nullable=False)
    unit_price = db.Column(db.Numeric(12, 2), nullable=False)
    tax_rate   = db.Column(db.Numeric(5, 2), nullable=False, default=0.00)
    notes      = db.Column(db.Text, nullable=True)
    station    = db.Column(db.String(40), nullable=False)
    is_refill  = db.Column(db.Boolean, nullable=False, default=False)
    printed_at = db.Column(db.DateTime(timezone=True), nullable=True)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False,
                           default=datetime.utcnow)

    # ⚠️  MIGRACIÓN: seat_number INTEGER fue reemplazado por seat_label VARCHAR(80)
    # Asegúrate de haber aplicado:
    #   ALTER TABLE order_items DROP COLUMN seat_number;
    #   ALTER TABLE order_items ADD COLUMN seat_label VARCHAR(80);
    seat_label = db.Column(db.String(80), nullable=True)

    __table_args__ = (
        CheckConstraint('qty > 0', name='order_items_qty_check'),
        CheckConstraint('unit_price >= 0', name='order_items_unit_price_check'),
    )

    def to_dict(self):
        return {
            'id':         str(self.id),
            'order_id':   str(self.order_id),
            'refill_id':  str(self.refill_id) if self.refill_id else None,
            'product_id': str(self.product_id),
            'qty':        float(self.qty),
            'unit_price': float(self.unit_price),
            'tax_rate':   float(self.tax_rate),
            'notes':      self.notes,
            'station':    self.station,
            'is_refill':  self.is_refill,
            'printed_at': self.printed_at.isoformat() if self.printed_at else None,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'seat_label': self.seat_label,
        }


# ---------------------------------------------------------------------------
# Payment
# ---------------------------------------------------------------------------

payment_method_enum = Enum(
    'cash', 'card', 'transfer', 'mixed',
    name='payment_method'
)

from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy import String

class Payment(db.Model):
    __tablename__ = 'payments'

    id              = db.Column(UUID(as_uuid=True), primary_key=True,
                                server_default=text("gen_random_uuid()"))
    branch_id       = db.Column(UUID(as_uuid=True),
                                db.ForeignKey('branches.id', ondelete='CASCADE'),
                                nullable=False)
    order_id        = db.Column(UUID(as_uuid=True),
                                db.ForeignKey('orders.id', ondelete='CASCADE'),
                                nullable=False)
    method          = db.Column(payment_method_enum, nullable=False)
    amount          = db.Column(db.Numeric(12, 2), nullable=False)
    tip_amount      = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    received_amount = db.Column(db.Numeric(12, 2), nullable=True)   # efectivo recibido
    change_amount   = db.Column(db.Numeric(12, 2), nullable=True)   # cambio devuelto
    seat_labels     = db.Column(ARRAY(String), nullable=True)        # asientos cubiertos
    received_by     = db.Column(UUID(as_uuid=True),
                                db.ForeignKey('users.id', ondelete='RESTRICT'),
                                nullable=False)
    paid_at         = db.Column(db.DateTime(timezone=True), nullable=False,
                                default=datetime.utcnow)
    notes           = db.Column(db.Text, nullable=True)

    __table_args__ = (
        CheckConstraint('amount > 0', name='payments_amount_check'),
    )

    def to_dict(self):
        return {
            'id':              str(self.id),
            'branch_id':       str(self.branch_id),
            'order_id':        str(self.order_id),
            'method':          self.method,
            'amount':          float(self.amount),
            'tip_amount':      float(self.tip_amount),
            'received_amount': float(self.received_amount) if self.received_amount else None,
            'change_amount':   float(self.change_amount) if self.change_amount else None,
            'seat_labels':     self.seat_labels,
            'received_by':     str(self.received_by),
            'paid_at':         self.paid_at.isoformat() if self.paid_at else None,
            'notes':           self.notes,
        }


# ---------------------------------------------------------------------------
# PrintJob
# ---------------------------------------------------------------------------

class PrintJob(db.Model):
    __tablename__ = 'print_jobs'

    id         = db.Column(UUID(as_uuid=True), primary_key=True,
                           server_default=text("gen_random_uuid()"))
    branch_id  = db.Column(UUID(as_uuid=True),
                           db.ForeignKey('branches.id', ondelete='CASCADE'),
                           nullable=False)
    order_id   = db.Column(UUID(as_uuid=True),
                           db.ForeignKey('orders.id', ondelete='CASCADE'),
                           nullable=False)
    printer_id = db.Column(UUID(as_uuid=True),
                           db.ForeignKey('printers.id', ondelete='RESTRICT'),
                           nullable=False)
    job_type   = db.Column(db.String(20), nullable=False)   # 'kitchen' | 'cashier'
    status     = db.Column(sync_status_enum, nullable=False, server_default='pending')
    payload    = db.Column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    attempts   = db.Column(db.Integer, nullable=False, default=0)
    last_error = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False,
                           default=datetime.utcnow)
    sent_at    = db.Column(db.DateTime(timezone=True), nullable=True)

    __table_args__ = (
        CheckConstraint("job_type IN ('kitchen', 'cashier', 'cashier_bill')",
                        name='print_jobs_job_type_check'),
    )

    def to_dict(self):
        return {
            'id':         str(self.id),
            'branch_id':  str(self.branch_id),
            'order_id':   str(self.order_id),
            'printer_id': str(self.printer_id),
            'job_type':   self.job_type,
            'status':     self.status,
            'payload':    self.payload,
            'attempts':   self.attempts,
            'last_error': self.last_error,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'sent_at':    self.sent_at.isoformat() if self.sent_at else None,
        }


# ---------------------------------------------------------------------------
# CashClosing
# ---------------------------------------------------------------------------

class CashClosing(db.Model):
    __tablename__ = 'cash_closings'

    id               = db.Column(UUID(as_uuid=True), primary_key=True,
                                 server_default=text("gen_random_uuid()"))
    branch_id        = db.Column(UUID(as_uuid=True),
                                 db.ForeignKey('branches.id', ondelete='CASCADE'),
                                 nullable=False)
    opened_by        = db.Column(UUID(as_uuid=True),
                                 db.ForeignKey('users.id', ondelete='RESTRICT'),
                                 nullable=False)
    closed_by        = db.Column(UUID(as_uuid=True),
                                 db.ForeignKey('users.id', ondelete='RESTRICT'),
                                 nullable=True)
    started_at       = db.Column(db.DateTime(timezone=True), nullable=False,
                                 default=datetime.utcnow)
    ended_at         = db.Column(db.DateTime(timezone=True), nullable=True)
    total_sales      = db.Column(db.Numeric(12, 2), nullable=False, default=0.00)
    total_cash       = db.Column(db.Numeric(12, 2), nullable=False, default=0.00)
    total_card       = db.Column(db.Numeric(12, 2), nullable=False, default=0.00)
    total_transfer   = db.Column(db.Numeric(12, 2), nullable=False, default=0.00)
    notes            = db.Column(db.Text, nullable=True)

    def to_dict(self):
        return {
            'id':             str(self.id),
            'branch_id':      str(self.branch_id),
            'opened_by':      str(self.opened_by),
            'closed_by':      str(self.closed_by) if self.closed_by else None,
            'started_at':     self.started_at.isoformat() if self.started_at else None,
            'ended_at':       self.ended_at.isoformat() if self.ended_at else None,
            'total_sales':    float(self.total_sales),
            'total_cash':     float(self.total_cash),
            'total_card':     float(self.total_card),
            'total_transfer': float(self.total_transfer),
            'notes':          self.notes,
        }


# ---------------------------------------------------------------------------
# AuditLog
# ---------------------------------------------------------------------------

class AuditLog(db.Model):
    __tablename__ = 'audit_logs'

    id          = db.Column(UUID(as_uuid=True), primary_key=True,
                            server_default=text("gen_random_uuid()"))
    branch_id   = db.Column(UUID(as_uuid=True),
                            db.ForeignKey('branches.id', ondelete='SET NULL'),
                            nullable=True)
    user_id     = db.Column(UUID(as_uuid=True),
                            db.ForeignKey('users.id', ondelete='SET NULL'),
                            nullable=True)
    entity_name = db.Column(db.String(80), nullable=False)
    entity_id   = db.Column(UUID(as_uuid=True), nullable=True)
    action      = db.Column(db.String(40), nullable=False)
    payload     = db.Column(JSONB, nullable=False,
                            server_default=text("'{}'::jsonb"))
    created_at  = db.Column(db.DateTime(timezone=True), nullable=False,
                            default=datetime.utcnow)

    def to_dict(self):
        return {
            'id':          str(self.id),
            'branch_id':   str(self.branch_id) if self.branch_id else None,
            'user_id':     str(self.user_id) if self.user_id else None,
            'entity_name': self.entity_name,
            'entity_id':   str(self.entity_id) if self.entity_id else None,
            'action':      self.action,
            'payload':     self.payload,
            'created_at':  self.created_at.isoformat() if self.created_at else None,
        }