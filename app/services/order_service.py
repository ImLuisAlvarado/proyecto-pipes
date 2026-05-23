from uuid import UUID
from flask import abort
from app.repositories.order_repository import OrderRepository
from app.models.order import Order, OrderItem
from app.schemas.order import OrderCreate, OrderRefillCreate

class OrderService:
    
    def __init__(self):
        self.repository = OrderRepository()

    def get_order_by_id(self, order_id: UUID) -> Order:
        """Obtiene una orden detallada o levanta un 404 si no existe."""
        order = self.repository.get_by_id(order_id)
        if not order:
            abort(404, description="La orden especificada no existe.")
        return order

    def create_new_order(self, order_data: OrderCreate) -> Order:
        """Procesa las reglas de negocio para abrir una nueva comanda."""
        # Instanciamos la cabecera del modelo con los datos validados por Pydantic
        new_order = Order(
            branch_id=order_data.branch_id,
            table_id=order_data.table_id,
            opened_by=order_data.opened_by,
            customer_id=order_data.customer_id,
            notes=order_data.notes,
            status='open'  # Estado inicial por defecto de tu ENUM
        )

        # Convertimos los esquemas de items iniciales a modelos de SQLAlchemy
        initial_items = []
        for item_schema in order_data.items:
            item_model = OrderItem(
                product_id=item_schema.product_id,
                qty=item_schema.qty,
                unit_price=item_schema.unit_price,
                tax_rate=item_schema.tax_rate,
                notes=item_schema.notes,
                station=item_schema.station,
                is_refill=item_schema.is_refill
            )
            initial_items.append(item_model)

        # 1. Guardamos la orden e items en la base de datos
        order = self.repository.create_order(new_order, initial_items)
        
        # 2. Si la orden se abrió con items, calculamos los totales de inmediato
        if initial_items:
            order = self.repository.update_order_totals(order.id)
            
        return order

    def request_order_refill(self, order_id: UUID, refill_data: OrderRefillCreate) -> Order:
        """Añade una ronda de refills a una comanda abierta y actualiza la cuenta."""
        # Regla de negocio: Validar que la orden exista y esté abierta para consumo
        order = self.get_order_by_id(order_id)
        
        if order.status in ['closed', 'cancelled']:
            abort(400, description=f"No se pueden solicitar refills. La orden se encuentra en estado: {order.status}")

        # Mapeamos los items del esquema a modelos de SQLAlchemy
        refill_items = []
        for item_schema in refill_data.items:
            item_model = OrderItem(
                product_id=item_schema.product_id,
                qty=item_schema.qty,
                unit_price=item_schema.unit_price,
                tax_rate=item_schema.tax_rate,
                notes=item_schema.notes,
                station=item_schema.station,
                is_refill=True  # Obligatorio por lógica de negocio de refill rápido
            )
            refill_items.append(item_model)

        # 1. Registramos la ronda de refill en la base de datos
        self.repository.add_refill_round(
            order_id=order_id,
            created_by=refill_data.created_by,
            reason=refill_data.reason,
            items=refill_items
        )

        # 2. Recalculamos el total de la cuenta acumulada de la mesa
        updated_order = self.repository.update_order_totals(order_id)
        return updated_order
    
    def close_account(self, order_id: UUID, closed_by: UUID) -> Order:
        """Aplica las reglas de negocio antes de cerrar la cuenta."""
        order = self.get_order_by_id(order_id)
        
        if order.status in ['closed', 'cancelled']:
            abort(400, description=f"La orden ya se encuentra {order.status}.")
            
        return self.repository.close_order(order_id, closed_by)