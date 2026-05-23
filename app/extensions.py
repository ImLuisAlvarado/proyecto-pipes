from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate

# Instanciamos sin acoplarlas a una app todavía
db = SQLAlchemy()
migrate = Migrate()