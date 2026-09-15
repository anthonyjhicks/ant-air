"""JWT authentication for the /api/v1/ endpoints."""

from datetime import datetime, timedelta, timezone
from functools import wraps

import jwt
from flask import current_app, g, jsonify, request

from .extensions import db
from .models import ApiUser


def create_access_token(user, client_id=None):
    """Create a JWT access token for the given user."""
    expires = timedelta(seconds=current_app.config["JWT_ACCESS_TOKEN_EXPIRES"])
    payload = {
        "sub": user.username,
        "user_id": user.id,
        "type": "access",
        "iat": datetime.now(timezone.utc),
        "exp": datetime.now(timezone.utc) + expires,
    }
    if client_id:
        payload["client_id"] = client_id
    return jwt.encode(payload, current_app.config["JWT_SECRET_KEY"], algorithm="HS256")


def create_refresh_token(user, client_id=None):
    """Create a JWT refresh token for the given user."""
    expires = timedelta(seconds=current_app.config["JWT_REFRESH_TOKEN_EXPIRES"])
    payload = {
        "sub": user.username,
        "user_id": user.id,
        "type": "refresh",
        "iat": datetime.now(timezone.utc),
        "exp": datetime.now(timezone.utc) + expires,
    }
    if client_id:
        payload["client_id"] = client_id
    return jwt.encode(payload, current_app.config["JWT_SECRET_KEY"], algorithm="HS256")


def decode_token(token):
    """Decode and validate a JWT token. Returns the payload dict or None."""
    try:
        return jwt.decode(
            token, current_app.config["JWT_SECRET_KEY"], algorithms=["HS256"]
        )
    except jwt.ExpiredSignatureError:
        return None
    except jwt.InvalidTokenError:
        return None


def require_api_auth(f):
    """Decorator that requires a valid JWT access token."""

    @wraps(f)
    def decorated(*args, **kwargs):
        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            return jsonify({"error": "Missing or invalid Authorization header"}), 401

        token = auth_header[7:]
        payload = decode_token(token)
        if payload is None:
            return jsonify({"error": "Invalid or expired token"}), 401
        if payload.get("type") != "access":
            return jsonify({"error": "Invalid token type"}), 401

        user = ApiUser.query.filter_by(username=payload["sub"]).first()
        if user is None:
            return jsonify({"error": "User not found"}), 401

        g.current_user = user
        g.client_id = payload.get("client_id")
        return f(*args, **kwargs)

    return decorated
