# app/models/__init__.py
"""
Registro central de modelos.
Importar desde aquí garantiza que SQLAlchemy registre
todos los mappers antes de cualquier create_all() o migración.
"""

from app.models.core import (       # noqa: F401
    Branch,
    User,
    DiningTable,
    Customer,
    Category,
    Printer,
)

from app.models.product import Product   # noqa: F401

from app.models.order import (           # noqa: F401
    Order,
    OrderRefill,
    OrderItem,
    Payment,
    PrintJob,
    CashClosing,
    AuditLog,
)