"""
auth.py
────────
JWT authentication for two roles:
  • SuperAdmin  – identified by SUPER_ADMIN_EMAIL in settings
  • HRUser      – any active HRUser row

Token payload:
  { "role": "superadmin" | "hr", "user_id": <int|None>, "email": "..." }

Usage in views:
  @permission_classes([IsSuperAdmin])
  @permission_classes([IsHRUser])
"""

from __future__ import annotations

import datetime
import logging

import jwt
from django.conf import settings
from django.contrib.auth.hashers import check_password
from rest_framework.authentication import BaseAuthentication
from rest_framework.exceptions import AuthenticationFailed
from rest_framework.permissions import BasePermission

from .models import HRUser

logger = logging.getLogger(__name__)

SECRET = getattr(settings, "JWT_SECRET", settings.SECRET_KEY)
ALGORITHM = "HS256"
TOKEN_TTL_HOURS = 12


# ── Token helpers ───────────────────────────────────────────────────────────

def _make_token(payload: dict) -> str:
    payload = payload.copy()
    payload["exp"] = datetime.datetime.utcnow() + datetime.timedelta(hours=TOKEN_TTL_HOURS)
    return jwt.encode(payload, SECRET, algorithm=ALGORITHM)


def _decode_token(token: str) -> dict:
    try:
        return jwt.decode(token, SECRET, algorithms=[ALGORITHM])
    except jwt.ExpiredSignatureError:
        raise AuthenticationFailed("Token has expired.")
    except jwt.InvalidTokenError as exc:
        raise AuthenticationFailed(f"Invalid token: {exc}")


# ── Fake user objects (attached to request.user) ────────────────────────────

class SuperAdminPrincipal:
    is_authenticated = True
    role = "superadmin"

    def __init__(self, email: str):
        self.email = email


class HRPrincipal:
    is_authenticated = True
    role = "hr"

    def __init__(self, hr_user: HRUser):
        self.hr_user = hr_user
        self.email = hr_user.email
        self.name = hr_user.name


# ── DRF Authentication class ────────────────────────────────────────────────

class JWTAuthentication(BaseAuthentication):
    """
    Reads: Authorization: Bearer <token>
    Sets request.user to SuperAdminPrincipal or HRPrincipal.
    """

    def authenticate(self, request):
        header = request.headers.get("Authorization", "")
        if not header.startswith("Bearer "):
            return None  # Not our scheme – let DRF try others

        token = header[len("Bearer "):]
        payload = _decode_token(token)
        role = payload.get("role")

        if role == "superadmin":
            return SuperAdminPrincipal(email=payload["email"]), token

        if role == "hr":
            user_id = payload.get("user_id")
            try:
                hr_user = HRUser.objects.get(pk=user_id, is_active=True)
            except HRUser.DoesNotExist:
                raise AuthenticationFailed("HR user not found or deactivated.")
            return HRPrincipal(hr_user), token

        raise AuthenticationFailed("Unknown role in token.")


# ── Permission classes ───────────────────────────────────────────────────────

class IsSuperAdmin(BasePermission):
    def has_permission(self, request, view):
        return (
            request.user
            and request.user.is_authenticated
            and getattr(request.user, "role", None) == "superadmin"
        )


class IsHRUser(BasePermission):
    def has_permission(self, request, view):
        return (
            request.user
            and request.user.is_authenticated
            and getattr(request.user, "role", None) == "hr"
        )


class IsHROrSuperAdmin(BasePermission):
    def has_permission(self, request, view):
        return (
            request.user
            and request.user.is_authenticated
            and getattr(request.user, "role", None) in ("hr", "superadmin")
        )


# ── Login view helpers ───────────────────────────────────────────────────────

def login_superadmin(email: str, password: str) -> str:
    """
    Validate against SUPER_ADMIN_EMAIL + SUPER_ADMIN_PASSWORD in settings.
    Returns JWT token.
    """
    admin_email = getattr(settings, "SUPER_ADMIN_EMAIL", "")
    admin_password = getattr(settings, "SUPER_ADMIN_PASSWORD", "")

    if email != admin_email or password != admin_password:
        raise AuthenticationFailed("Invalid superadmin credentials.")

    return _make_token({"role": "superadmin", "email": email})


def login_hr(email: str, password: str) -> str:
    """Validate HR credentials. Returns JWT token."""
    try:
        hr_user = HRUser.objects.get(email=email, is_active=True)
    except HRUser.DoesNotExist:
        raise AuthenticationFailed("Invalid credentials.")

    if not check_password(password, hr_user.password):
        raise AuthenticationFailed("Invalid credentials.")

    return _make_token({"role": "hr", "user_id": hr_user.pk, "email": email})