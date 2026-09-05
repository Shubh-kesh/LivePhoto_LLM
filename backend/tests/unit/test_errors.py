"""Standard error envelope tests (M1 §18, §54)."""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from pydantic import BaseModel

from app.core.errors import ApiError
from app.factory import create_app


class _Payload(BaseModel):
    count: int


def _app_with_errors(settings) -> FastAPI:
    app = create_app(settings)

    @app.get("/boom")
    def boom() -> None:
        raise ApiError(code="THING_FAILED", message="The thing failed", status_code=409)

    @app.get("/unhandled")
    def unhandled() -> None:
        raise ValueError("secret-ish detail that must not leak")

    @app.post("/validate")
    def validate(payload: _Payload) -> _Payload:
        return payload

    @app.get("/echo-error-envelope")
    def echo(request: Request) -> dict[str, object]:
        from app.core.errors import ErrorEnvelope

        return ErrorEnvelope(
            error={
                "code": "X",
                "message": "Y",
                "request_id": request.scope.get("request_id", ""),
            }
        ).model_dump()

    return app


def test_api_error_envelope(settings) -> None:
    app = _app_with_errors(settings)
    with TestClient(app) as client:
        response = client.get("/boom")
    assert response.status_code == 409
    body = response.json()
    assert body["error"]["code"] == "THING_FAILED"
    assert body["error"]["message"] == "The thing failed"
    assert body["error"]["request_id"]


def test_404_uses_envelope(client) -> None:
    response = client.get("/nope")
    assert response.status_code == 404
    body = response.json()
    assert body["error"]["code"] == "NOT_FOUND"
    assert body["error"]["message"] == "Not Found"
    assert body["error"]["request_id"]


def test_validation_error_uses_envelope(settings) -> None:
    app = _app_with_errors(settings)
    with TestClient(app) as client:
        response = client.post("/validate", json={"count": "not-an-int"})
    assert response.status_code == 422
    body = response.json()
    assert body["error"]["code"] == "VALIDATION_ERROR"
    assert body["error"]["message"] == "Request validation failed"


def test_unhandled_error_is_sanitized(settings) -> None:
    app = _app_with_errors(settings)
    # raise_server_exceptions=False lets us observe the generated 500 envelope (Starlette
    # re-raises handled server errors to the client by default).
    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.get("/unhandled")
    assert response.status_code == 500
    body = response.json()
    assert body["error"]["code"] == "INTERNAL_ERROR"
    assert body["error"]["message"] == "Internal server error"
    # The exception detail must never reach the caller.
    assert "secret-ish" not in response.text


def test_envelope_shape_is_stable() -> None:
    from app.core.errors import ErrorDetail, ErrorEnvelope

    envelope = ErrorEnvelope(error=ErrorDetail(code="CODE", message="Msg", request_id="r1"))
    assert envelope.model_dump() == {
        "error": {"code": "CODE", "message": "Msg", "request_id": "r1"}
    }


def test_custom_error_route_uses_request_id(settings) -> None:
    app = _app_with_errors(settings)
    with TestClient(app) as client:
        response = client.get("/echo-error-envelope")
    body = response.json()
    assert body["error"]["request_id"] == response.headers.get("x-request-id")
