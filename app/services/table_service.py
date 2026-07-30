# app/services/table_service.py
from uuid import uuid4
from app.models.core import DiningTable
from app.repositories.table_repository import TableRepository

class TableService:
    def __init__(self):
        self.repo = TableRepository()

    def get_all_tables(self, branch_id=None):
        return self.repo.get_all(branch_id)

    def get_table_by_id(self, table_id):
        table = self.repo.get_by_id(table_id)
        if not table:
            raise ValueError("Mesa no encontrada")
        return table

    def create_table(self, schema):
        table = DiningTable(
            id=uuid4(),
            branch_id=schema.branch_id,
            code=schema.code,
            name=schema.name,
            seats=schema.seats,
            status=schema.status,
            active=schema.active
        )
        return self.repo.create(table)

    def update_table(self, table_id, schema):
        table = self.get_table_by_id(table_id)
        data = schema.model_dump(exclude_unset=True)
        for key, value in data.items():
            setattr(table, key, value)
        return self.repo.update(table)