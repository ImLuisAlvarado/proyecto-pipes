from flask import Flask
from app.config import Config
from app.extensions import db, migrate

def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)

    # 1. Inicializamos las extensiones con la app
    db.init_app(app)
    migrate.init_app(app, db)

    from app import models

    # 2. Registramos los Blueprints (Rutas de la API)
    from app.routes.order_routes import order_bp
    app.register_blueprint(order_bp)

    # Endpoint de prueba para verificar que el servidor está vivo
    @app.route('/health')
    def health_check():
        return {"status": "ok", "message": "Restaurant POS Backend is running"}

    return app