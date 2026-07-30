# app/__init__.py
from flask import Flask
from app.config import Config
from app.extensions import db, migrate


def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)

    db.init_app(app)
    migrate.init_app(app, db)

    from app import models  # noqa

    from app.routes.auth_routes     import auth_bp
    from app.routes.order_routes    import order_bp
    from app.routes.table_routes    import table_bp
    from app.routes.product_routes  import product_bp
    from app.routes.category_routes import category_bp   # ← nuevo

    app.register_blueprint(auth_bp)
    app.register_blueprint(order_bp)
    app.register_blueprint(table_bp)
    app.register_blueprint(product_bp)
    app.register_blueprint(category_bp)                  # ← nuevo

    @app.route('/health')
    def health_check():
        return {"status": "ok", "message": "Restaurant POS Backend is running"}

    return app