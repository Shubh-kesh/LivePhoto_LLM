"""Experiment endpoint tests (M4 §10-11, §15, §70-72, §128, §140)."""

from __future__ import annotations

import io

from fastapi.testclient import TestClient
from PIL import Image

from app.core.config import Settings
from app.factory import create_app


def _jpeg_bytes(width: int = 32, height: int = 32) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (width, height), (128, 128, 128)).save(buffer, format="JPEG")
    return buffer.getvalue()


def _settings(**overrides: object) -> Settings:
    defaults: dict[str, object] = {
        "app_env": "test",
        "vlm_experiment_enabled": True,
    }
    defaults.update(overrides)
    return Settings(_env_file=None, **defaults)  # type: ignore[arg-type]


def _files(count: int, data: bytes | None = None) -> list[tuple[str, bytes, str]]:
    payload = data if data is not None else _jpeg_bytes()
    return [("frames", (f"frame-{i}.jpg", payload, "image/jpeg")) for i in range(count)]


def _post(
    client: TestClient,
    files: list[tuple[str, tuple[str, bytes, str]]],
    strategy: str = "single-quality-v1",
):
    return client.post(
        "/api/v1/experiments/vlm/evaluate",
        data={"strategy": strategy, "provider": "mock", "frame_selection_version": strategy},
        files=files,
    )


def test_experiment_disabled_by_default() -> None:
    app = create_app(_settings(vlm_experiment_enabled=False))
    with TestClient(app) as client:
        response = _post(client, _files(1))
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "VLM_DISABLED"


def test_experiment_refused_in_uat_even_when_enabled() -> None:
    app = create_app(_settings(app_env="uat", vlm_experiment_enabled=True))
    with TestClient(app) as client:
        response = _post(client, _files(1))
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "VLM_DISABLED"


def test_experiment_success_with_mock_provider() -> None:
    app = create_app(_settings())
    with TestClient(app) as client:
        response = _post(client, _files(1))
    assert response.status_code == 200
    body = response.json()
    assert body["experiment"] is True
    assert body["provider"] == "mock"
    assert body["classification"] == "SCREEN_REPLAY"
    assert body["frame_strategy"] == "single-quality-v1"
    assert "latency_ms" in body


def test_providers_list_endpoint() -> None:
    app = create_app(_settings())
    with TestClient(app) as client:
        response = client.get("/api/v1/experiments/vlm/providers")
    assert response.status_code == 200
    assert "mock" in response.json()["providers"]


def test_strategy_frame_count_enforced() -> None:
    app = create_app(_settings())
    with TestClient(app) as client:
        response = _post(client, _files(2), strategy="single-quality-v1")
    assert response.status_code == 400


def test_too_many_frames_rejected() -> None:
    app = create_app(_settings(vlm_max_frames=3))
    with TestClient(app) as client:
        response = _post(client, _files(4), strategy="temporal-triad-v1")
    assert response.status_code == 400


def test_oversized_image_rejected() -> None:
    app = create_app(_settings(vlm_max_single_image_bytes=100))
    with TestClient(app) as client:
        response = _post(client, _files(1))
    assert response.status_code == 413
    assert response.json()["error"]["code"] == "REQUEST_TOO_LARGE"


def test_non_jpeg_signature_rejected() -> None:
    app = create_app(_settings())
    with TestClient(app) as client:
        response = _post(client, _files(1, data=b"not a jpeg at all, definitely not"))
    assert response.status_code == 415
    assert response.json()["error"]["code"] == "UNSUPPORTED_MEDIA_TYPE"


def test_undecodeable_jpeg_rejected() -> None:
    # Valid JPEG signature but malformed body -> cannot be decoded.
    app = create_app(_settings())
    with TestClient(app) as client:
        response = _post(client, _files(1, data=b"\xff\xd8\xff" + b"\x00" * 64))
    assert response.status_code == 415


def test_triad_strategy_three_frames() -> None:
    app = create_app(_settings())
    with TestClient(app) as client:
        response = _post(client, _files(3), strategy="temporal-triad-v1")
    assert response.status_code == 200
    assert response.json()["image_count"] == 3


def test_no_browser_base64_json_upload_used() -> None:
    # The endpoint only accepts multipart; a JSON body must fail (415/422), not evaluate.
    app = create_app(_settings())
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/experiments/vlm/evaluate",
            json={"provider": "mock", "strategy": "single-quality-v1", "frames_b64": ["xxx"]},
        )
    assert response.status_code in (415, 422)
