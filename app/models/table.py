# app/models/table.py
"""
DiningTable está definido en core.py junto a los demás modelos base.
Este archivo re-exporta el modelo para mantener compatibilidad con
cualquier import existente que lo busque aquí.
"""

from app.models.core import DiningTable  # noqa: F401

# Alias para compatibilidad con repositorios que importen TableModel
TableModel = DiningTable