# app/repositories/table_repository.py
from app.models.core import DiningTable as TableModel
from app.extensions import db

class TableRepository:
    def get_all(self, branch_id=None):
        query = TableModel.query
        if branch_id:
            query = query.filter_by(branch_id=branch_id)
        return query.order_by(TableModel.code.asc()).all()

    def get_by_id(self, table_id):
        return TableModel.query.get(table_id)

    def create(self, table):
        db.session.add(table)
        db.session.commit()
        return table

    def update(self, table):
        db.session.commit()
        return table