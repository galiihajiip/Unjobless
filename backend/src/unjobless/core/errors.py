"""Predictable application errors mapped to HTTP responses."""

from __future__ import annotations

from typing import Any


class AppError(Exception):
    status_code = 400
    code = "bad_request"

    def __init__(self, message: str, *, details: dict[str, Any] | None = None, code: str | None = None):
        super().__init__(message)
        self.message = message
        self.details = details or {}
        if code:
            self.code = code


class NotFound(AppError):
    status_code = 404
    code = "not_found"


class Conflict(AppError):
    status_code = 409
    code = "conflict"


class ValidationFailed(AppError):
    status_code = 422
    code = "validation_failed"


class Unauthorized(AppError):
    status_code = 401
    code = "unauthorized"


class Forbidden(AppError):
    status_code = 403
    code = "forbidden"


class TooManyRequests(AppError):
    status_code = 429
    code = "too_many_requests"


class InvalidTransition(AppError):
    status_code = 409
    code = "invalid_transition"


class BlockedURL(AppError):
    """URL rejected by SSRF / policy guards."""

    status_code = 422
    code = "blocked_url"


class FetchFailed(AppError):
    status_code = 502
    code = "fetch_failed"
