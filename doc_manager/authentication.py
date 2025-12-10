from __future__ import annotations

import os
from datetime import datetime, timedelta
from typing import Optional, Tuple

import jwt
from django.contrib.auth.models import User
from rest_framework.authentication import BaseAuthentication
from rest_framework.request import Request
from rest_framework.exceptions import AuthenticationFailed

class AdminTokenAuthentication(BaseAuthentication):
    """
    JWT-based authentication for the admin user.
    The token is expected to be in the 'Authorization' header,
    with the 'Bearer' scheme.
    e.g., 'Authorization: Bearer <your-jwt-token>'
    """

    def authenticate(self, request: Request) -> Optional[Tuple[User, None]]:
        auth_header = request.headers.get("Authorization")
        if not auth_header:
            return None

        try:
            scheme, token = auth_header.split()
        except ValueError:
            raise AuthenticationFailed("Invalid authorization header.")

        if scheme.lower() != "bearer":
            raise AuthenticationFailed("Invalid authorization scheme.")

        secret_key = os.getenv("JWT_SECRET_KEY", "your-secret-key-change-in-production")
        try:
            payload = jwt.decode(token, secret_key, algorithms=["HS256"])
        except jwt.ExpiredSignatureError:
            raise AuthenticationFailed("Token has expired.")
        except jwt.InvalidTokenError:
            raise AuthenticationFailed("Invalid token.")

        username = payload.get("username")
        if username != "admin":
            raise AuthenticationFailed("Invalid token for admin user.")

        # We need a user object for Django REST Framework, but we're not using
        # Django's user database for this. We can create a temporary, unsaved
        # user object.
        user = User(username="admin", is_staff=True, is_superuser=True)
        return (user, None)

    def authenticate_header(self, request: Request) -> str:
        return 'Bearer realm="api"'


def generate_admin_token(expires_in_hours: int = 24) -> str:
    """
    Generate a JWT token for the admin user.
    
    Args:
        expires_in_hours: Token expiration time in hours (default: 24)
    
    Returns:
        JWT token string
    """
    secret_key = os.getenv("JWT_SECRET_KEY", "your-secret-key-change-in-production")
    payload = {
        "username": "admin",
        "exp": datetime.utcnow() + timedelta(hours=expires_in_hours),
        "iat": datetime.utcnow(),
    }
    return jwt.encode(payload, secret_key, algorithm="HS256")
