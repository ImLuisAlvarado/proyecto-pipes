from sqlalchemy.dialects.postgresql import UUID
from app.extensions import db

class Branch(db.Model):
    __tablename__ = 'branches'
    id = db.Column(UUID(as_uuid=True), primary_key=True)

class User(db.Model):
    __tablename__ = 'users'
    id = db.Column(UUID(as_uuid=True), primary_key=True)

class DiningTable(db.Model):
    __tablename__ = 'dining_tables'
    id = db.Column(UUID(as_uuid=True), primary_key=True)

class Customer(db.Model):
    __tablename__ = 'customers'
    id = db.Column(UUID(as_uuid=True), primary_key=True)

class Product(db.Model):
    __tablename__ = 'products'
    id = db.Column(UUID(as_uuid=True), primary_key=True)