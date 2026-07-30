import os
from datetime import datetime, timedelta, timezone

import jwt
import bcrypt
from flask import Blueprint, request, jsonify, g
from pydantic import ValidationError

from app.extensions import db
from app.models.core import User
from app.schemas.auth import LoginRequest, AuthResponse
from app.schemas.user import UserResponse

auth_bp = Blueprint('auth', __name__, url_prefix='/api/v1/auth')

JWT_SECRET      = os.environ.get('JWT_SECRET', 'dev-secret-change-in-production')
JWT_ALGORITHM   = 'HS256'
ACCESS_EXPIRES  = timedelta(hours=8)
REFRESH_EXPIRES = timedelta(days=30)


def _make_tokens(user_id: str) -> tuple[str, str]:
    now = datetime.now(timezone.utc)

    access = jwt.encode({
        'sub': user_id,
        'iat': now,
        'exp': now + ACCESS_EXPIRES,
        'type': 'access',
    }, JWT_SECRET, algorithm=JWT_ALGORITHM)

    refresh = jwt.encode({
        'sub': user_id,
        'iat': now,
        'exp': now + REFRESH_EXPIRES,
        'type': 'refresh',
    }, JWT_SECRET, algorithm=JWT_ALGORITHM)

    return access, refresh


def verify_token(token: str) -> dict | None:
    """Decodifica y valida el JWT. Retorna payload o None si es inválido."""
    try:
        return jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except jwt.PyJWTError:
        return None


# ── POST /api/v1/auth/login ────────────────────────────────────────────────

@auth_bp.route('/login', methods=['POST'])
def login():
    json_data = request.get_json()
    if not json_data:
        return jsonify({"error": "Cuerpo vacío"}), 400

    try:
        body = LoginRequest(**json_data)
    except ValidationError as e:
        return jsonify({"error": "Validación", "details": e.errors(include_url=False)}), 422

    user = User.query.filter_by(username=body.username, active=True).first()

    if not user:
        return jsonify({"error": "Credenciales inválidas"}), 401

    # Verificar password con bcrypt
    # Si tu hash fue generado con otro método, ajusta esta línea
    try:
        password_ok = bcrypt.checkpw(
            body.password.encode('utf-8'),
            user.password_hash.encode('utf-8')
        )
    except Exception:
        password_ok = False

    if not password_ok:
        return jsonify({"error": "Credenciales inválidas"}), 401

    access_token, refresh_token = _make_tokens(str(user.id))

    response = AuthResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        user=UserResponse.model_validate(user),
    )

    return jsonify(response.model_dump()), 200


# ── GET /api/v1/auth/me ────────────────────────────────────────────────────

@auth_bp.route('/me', methods=['GET'])
def get_me():
    auth_header = request.headers.get('Authorization', '')
    if not auth_header.startswith('Bearer '):
        return jsonify({"error": "Token requerido"}), 401

    token = auth_header.removeprefix('Bearer ').strip()
    payload = verify_token(token)

    if not payload or payload.get('type') != 'access':
        return jsonify({"error": "Token inválido o expirado"}), 401

    user = User.query.get(payload['sub'])
    if not user or not user.active:
        return jsonify({"error": "Usuario no encontrado"}), 404

    return jsonify(UserResponse.model_validate(user).model_dump(mode='json')), 200