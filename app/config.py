import os
from dotenv import load_dotenv

# Carga las variables del archivo .env a las variables de entorno del sistema
load_dotenv()

class Config:
    # Clave secreta para sesiones y seguridad
    SECRET_KEY = os.getenv('SECRET_KEY', 'dev-super-secret-key')
    
    # URL de conexión a PostgreSQL
    # Formato esperado: postgresql://usuario:password@localhost:5432/nombre_bd
    SQLALCHEMY_DATABASE_URI = os.getenv('DATABASE_URL')
    
    # Desactiva los avisos molestos y optimiza memoria
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    
    # Configuraciones extra para que Pydantic devuelva JSON limpios si se requiere
    JSON_SORT_KEYS = False