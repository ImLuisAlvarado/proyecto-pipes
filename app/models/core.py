# app/models/core.py
"""
Modelos base / catálogos del sistema.
Todos los modelos están definidos aquí o en sus propios archivos;
este módulo ya NO contiene stubs vacíos para evitar conflictos
con los modelos reales al momento de la inicialización de SQLAlchemy.
"""

from datetime import datetime
from sqlalchemy.dialects.postgresql import UUID, INET, JSONB
from sqlalchemy import Enum, text
from app.extensions import db

user_role_enum = Enum(
    'admin', 'cashier', 'waiter', 'kitchen',
    name='user_role'
)

table_status_enum = Enum(
    'available', 'occupied', 'reserved', 'closed',
    name='table_status'
)

printer_type_enum = Enum(
    'kitchen', 'cashier',
    name='printer_type'
)

payment_method_enum = Enum(
    'cash', 'card', 'transfer', 'mixed',
    name='payment_method'
)

class Branch(db.Model):
    __tablename__ = 'branches'

    id           = db.Column(UUID(as_uuid=True), primary_key=True,
                             server_default=text("gen_random_uuid()"))
    name         = db.Column(db.String(120), nullable=False)
    address      = db.Column(db.Text, nullable=True)
    phone        = db.Column(db.String(30), nullable=True)
    active       = db.Column(db.Boolean, nullable=False, default=True)
    created_at   = db.Column(db.DateTime(timezone=True), nullable=False,
                             default=datetime.utcnow)
    updated_at   = db.Column(db.DateTime(timezone=True), nullable=False,
                             default=datetime.utcnow, onupdate=datetime.utcnow)

    def to_dict(self):
        return {
            'id':         str(self.id),
            'name':       self.name,
            'address':    self.address,
            'phone':      self.phone,
            'active':     self.active,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
        }

class User(db.Model):
    __tablename__ = 'users'

    id            = db.Column(UUID(as_uuid=True), primary_key=True,
                              server_default=text("gen_random_uuid()"))
    branch_id     = db.Column(UUID(as_uuid=True),
                              db.ForeignKey('branches.id', ondelete='SET NULL'),
                              nullable=True)
    full_name     = db.Column(db.String(120), nullable=False)
    username      = db.Column(db.String(60), nullable=False, unique=True)
    password_hash = db.Column(db.Text, nullable=False)
    role          = db.Column(user_role_enum, nullable=False, server_default='waiter')
    active        = db.Column(db.Boolean, nullable=False, default=True)
    created_at    = db.Column(db.DateTime(timezone=True), nullable=False,
                              default=datetime.utcnow)
    updated_at    = db.Column(db.DateTime(timezone=True), nullable=False,
                              default=datetime.utcnow, onupdate=datetime.utcnow)

    def to_dict(self):
        return {
            'id':        str(self.id),
            'branch_id': str(self.branch_id) if self.branch_id else None,
            'full_name': self.full_name,
            'username':  self.username,
            'role':      self.role,
            'active':    self.active,
        }

class DiningTable(db.Model):
    __tablename__ = 'dining_tables'

    id         = db.Column(UUID(as_uuid=True), primary_key=True,
                           server_default=text("gen_random_uuid()"))
    branch_id  = db.Column(UUID(as_uuid=True),
                           db.ForeignKey('branches.id', ondelete='CASCADE'),
                           nullable=False)
    code       = db.Column(db.String(20), nullable=False)
    name       = db.Column(db.String(60), nullable=False)
    seats      = db.Column(db.Integer, nullable=False, server_default=text("4"))
    status     = db.Column(table_status_enum, nullable=False,
                           server_default='available')
    active     = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False,
                           default=datetime.utcnow)
    updated_at = db.Column(db.DateTime(timezone=True), nullable=False,
                           default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        db.UniqueConstraint('branch_id', 'code', name='uq_dining_tables_branch_code'),
    )

    def to_dict(self):
        return {
            'id':        str(self.id),
            'branch_id': str(self.branch_id),
            'code':      self.code,
            'name':      self.name,
            'seats':     self.seats,
            'status':    self.status,
            'active':    self.active,
        }


class Customer(db.Model):
    __tablename__ = 'customers'

    id         = db.Column(UUID(as_uuid=True), primary_key=True,
                           server_default=text("gen_random_uuid()"))
    branch_id  = db.Column(UUID(as_uuid=True),
                           db.ForeignKey('branches.id', ondelete='SET NULL'),
                           nullable=True)
    full_name  = db.Column(db.String(120), nullable=True)
    phone      = db.Column(db.String(30), nullable=True)
    notes      = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False,
                           default=datetime.utcnow)
    updated_at = db.Column(db.DateTime(timezone=True), nullable=False,
                           default=datetime.utcnow, onupdate=datetime.utcnow)

    def to_dict(self):
        return {
            'id':        str(self.id),
            'branch_id': str(self.branch_id) if self.branch_id else None,
            'full_name': self.full_name,
            'phone':     self.phone,
            'notes':     self.notes,
        }


class Category(db.Model):
    __tablename__ = 'categories'

    id         = db.Column(UUID(as_uuid=True), primary_key=True,
                           server_default=text("gen_random_uuid()"))
    branch_id  = db.Column(UUID(as_uuid=True),
                           db.ForeignKey('branches.id', ondelete='CASCADE'),
                           nullable=True)
    name       = db.Column(db.String(80), nullable=False)
    sort_order = db.Column(db.Integer, nullable=False, default=0)
    active     = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False,
                           default=datetime.utcnow)
    updated_at = db.Column(db.DateTime(timezone=True), nullable=False,
                           default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        db.UniqueConstraint('branch_id', 'name', name='uq_categories_branch_name'),
    )

    products = db.relationship('Product', backref='category', lazy=True)

    def to_dict(self):
        return {
            'id':         str(self.id),
            'branch_id':  str(self.branch_id) if self.branch_id else None,
            'name':       self.name,
            'sort_order': self.sort_order,
            'active':     self.active,
        }


class Printer(db.Model):
    __tablename__ = 'printers'

    id         = db.Column(UUID(as_uuid=True), primary_key=True,
                           server_default=text("gen_random_uuid()"))
    branch_id  = db.Column(UUID(as_uuid=True),
                           db.ForeignKey('branches.id', ondelete='CASCADE'),
                           nullable=False)
    name       = db.Column(db.String(80), nullable=False)
    type       = db.Column(printer_type_enum, nullable=False)
    ip_address = db.Column(INET, nullable=False)
    port       = db.Column(db.Integer, nullable=False, default=9100)
    station    = db.Column(db.String(40), nullable=False)
    active     = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False,
                           default=datetime.utcnow)
    updated_at = db.Column(db.DateTime(timezone=True), nullable=False,
                           default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        db.UniqueConstraint('branch_id', 'name', name='uq_printers_branch_name'),
    )

    def to_dict(self):
        return {
            'id':         str(self.id),
            'branch_id':  str(self.branch_id),
            'name':       self.name,
            'type':       self.type,
            'ip_address': str(self.ip_address),
            'port':       self.port,
            'station':    self.station,
            'active':     self.active,
        }