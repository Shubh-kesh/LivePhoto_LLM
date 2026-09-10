"""Transaction + portrait API tests (M5.7 §106)."""

from __future__ import annotations

import io

from fastapi.testclient import TestClient
from PIL import Image

from app.core.config import Settings
from app.factory import create_app
from app.transactions import TransactionFileStore


def _jpeg_bytes(width: int = 96, height: int = 128) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (width, height), (110, 130, 150)).save(buffer, format="JPEG")
    return buffer.getvalue()


def _make_app(tmp_path, **overrides: object):
    settings_kwargs: dict[str, object] = {
        "app_env": "test",
        "vlm_experiment_enabled": True,
        "file_storage_root": str(tmp_path / "storage"),
        "portrait_processing_enabled": True,
        "portrait_background_color": "#FFFFFF",
    }
    settings_kwargs.update(overrides)
    settings = Settings(_env_file=None, **settings_kwargs)  # type: ignore[arg-type]
    app = create_app(settings)
    # Inject a deterministic segmentation matte so no real model is required in CI (M5.7 §85).
    from app.portrait import FakePortraitSegmentation

    app.state.portrait_segmentation = FakePortraitSegmentation()
    return app


def _create_transaction(client: TestClient) -> str:
    response = client.post(
        "/api/v1/transactions",
        files={"image": ("sel.jpg", _jpeg_bytes(), "image/jpeg")},
        data={"capture_config_version": "capture-v1", "quality_config_version": "quality-v1"},
    )
    assert response.status_code == 200, response.text
    return response.json()["transaction_id"]


def _persist_vlm(client: TestClient, transaction_id: str, classification: str) -> None:
    store: TransactionFileStore = client.app.state.transaction_store
    import json as _json

    from app.transactions import ArtifactType

    store.write_artifact(
        transaction_id,
        ArtifactType.VLM_RESULT,
        _json.dumps(
            {
                "provider": "mock",
                "model": "mock-vision-v1",
                "classification": classification,
                "attack_medium": "NONE",
                "self_reported_confidence": 0.9,
                "evidence_codes": [],
                "latency_ms": 1,
                "experiment_id": "e" * 32,
                "request_id": "r" * 32,
            }
        ).encode(),
        content_type="application/json",
    )


def test_create_transaction_persists_capture(tmp_path) -> None:
    app = _make_app(tmp_path)
    with TestClient(app) as client:
        tx_id = _create_transaction(client)
    store: TransactionFileStore = app.state.transaction_store
    assert store.transaction_exists(tx_id)
    assert store.artifact_exists(tx_id, "capture/selected-original.jpg")
    assert store.read_transaction_json(tx_id)["status"] == "CAPTURE_READY"


def test_vlm_result_persisted_on_evaluate(tmp_path) -> None:
    app = _make_app(tmp_path)
    with TestClient(app) as client:
        tx_id = _create_transaction(client)
        response = client.post(
            "/api/v1/experiments/vlm/evaluate",
            data={
                "strategy": "single-quality-v1",
                "provider": "mock",
                "mock_behavior": "live",
                "transaction_id": tx_id,
                "frame_selection_version": "single-quality-v1",
            },
            files={"frames": ("frame-0.jpg", _jpeg_bytes(), "image/jpeg")},
        )
        assert response.status_code == 200, response.text
        assert response.json()["classification"] == "LIVE"
        assert response.json()["transaction_id"] == tx_id
    store: TransactionFileStore = app.state.transaction_store
    result = store.read_json(tx_id, "vlm/result.json")
    assert result["classification"] == "LIVE"
    assert store.read_transaction_json(tx_id)["status"] == "VLM_EVALUATED"


def test_live_triggers_portrait_processing(tmp_path) -> None:
    app = _make_app(tmp_path)
    with TestClient(app) as client:
        tx_id = _create_transaction(client)
        _persist_vlm(client, tx_id, "LIVE")
        response = client.post(f"/api/v1/transactions/{tx_id}/portrait")
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["status"] == "SUCCESS"
        assert body["output_artifact"]["relative_path"] == "portrait/processed.jpg"
    store: TransactionFileStore = app.state.transaction_store
    assert store.artifact_exists(tx_id, "portrait/processed.jpg")
    meta = store.read_json(tx_id, "portrait/processing.json")
    assert meta["status"] == "SUCCESS"
    assert store.read_transaction_json(tx_id)["status"] == "PORTRAIT_READY"


def test_non_live_does_not_trigger(tmp_path) -> None:
    app = _make_app(tmp_path)
    with TestClient(app) as client:
        tx_id = _create_transaction(client)
        _persist_vlm(client, tx_id, "SCREEN_REPLAY")
        response = client.post(f"/api/v1/transactions/{tx_id}/portrait")
        assert response.status_code == 500
        assert response.json()["error"]["code"] == "PORTRAIT_PROCESSING_FAILED"
    store: TransactionFileStore = app.state.transaction_store
    assert not store.artifact_exists(tx_id, "portrait/processed.jpg")


def test_portrait_disabled_rejected(tmp_path) -> None:
    app = _make_app(tmp_path, portrait_processing_enabled=False)
    with TestClient(app) as client:
        tx_id = _create_transaction(client)
        _persist_vlm(client, tx_id, "LIVE")
        response = client.post(f"/api/v1/transactions/{tx_id}/portrait")
        assert response.status_code == 500
        assert response.json()["error"]["code"] == "PORTRAIT_PROCESSING_FAILED"


def test_processed_artifact_retrieval(tmp_path) -> None:
    app = _make_app(tmp_path)
    with TestClient(app) as client:
        tx_id = _create_transaction(client)
        _persist_vlm(client, tx_id, "LIVE")
        client.post(f"/api/v1/transactions/{tx_id}/portrait")
        response = client.get(f"/api/v1/transactions/{tx_id}/artifacts/PROCESSED_PORTRAIT")
        assert response.status_code == 200
        assert response.headers["content-type"] == "image/jpeg"
        assert response.headers["cache-control"] == "no-store"
        assert response.content.startswith(b"\xff\xd8\xff")
    store: TransactionFileStore = app.state.transaction_store
    assert store.artifact_exists(tx_id, "portrait/processed.jpg")


def test_invalid_transaction_id_rejected(tmp_path) -> None:
    app = _make_app(tmp_path)
    with TestClient(app) as client:
        # A traversal string never reaches a handler (route 404); an invalid single-segment id is
        # rejected by the handler (400).
        assert (
            client.get(
                "/api/v1/transactions/../../etc/passwd/artifacts/PROCESSED_PORTRAIT"
            ).status_code
            == 404
        )
        response = client.get("/api/v1/transactions/abc/artifacts/PROCESSED_PORTRAIT")
        assert response.status_code == 400


def test_missing_artifact_404(tmp_path) -> None:
    app = _make_app(tmp_path)
    with TestClient(app) as client:
        tx_id = _create_transaction(client)
        response = client.get(f"/api/v1/transactions/{tx_id}/artifacts/PROCESSED_PORTRAIT")
        assert response.status_code == 404


def test_unknown_artifact_type_rejected(tmp_path) -> None:
    app = _make_app(tmp_path)
    with TestClient(app) as client:
        tx_id = _create_transaction(client)
        response = client.get(f"/api/v1/transactions/{tx_id}/artifacts/ARBITRARY_FILE")
        assert response.status_code == 400


def test_storage_readiness_ok(tmp_path) -> None:
    app = _make_app(tmp_path)
    with TestClient(app) as client:
        response = client.get("/health/ready")
        assert response.status_code == 200
        names = [check["name"] for check in response.json()["checks"]]
        assert "file_storage" in names


def test_transaction_liveness_live_allows_portrait(tmp_path) -> None:
    """Transaction liveness: backend LIVE -> outcome PASS, portrait endpoint succeeds."""
    app = _make_app(tmp_path, vlm_provider="mock", vlm_mock_behavior="live")
    with TestClient(app) as client:
        tx_id = _create_transaction(client)
        response = client.post(f"/api/v1/transactions/{tx_id}/liveness")
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["classification"] == "LIVE"
        assert body["outcome"] == "PASS"
        assert body["portrait_allowed"] is True
        portrait = client.post(f"/api/v1/transactions/{tx_id}/portrait")
        assert portrait.status_code == 200, portrait.text
    store: TransactionFileStore = app.state.transaction_store
    assert store.artifact_exists(tx_id, "portrait/processed.jpg")


def test_transaction_liveness_non_live_blocks_portrait(tmp_path) -> None:
    """Transaction liveness: non-LIVE -> FAIL, portrait endpoint stays blocked."""
    app = _make_app(tmp_path, vlm_provider="mock", vlm_mock_behavior="screen_replay")
    with TestClient(app) as client:
        tx_id = _create_transaction(client)
        response = client.post(f"/api/v1/transactions/{tx_id}/liveness")
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["classification"] == "SCREEN_REPLAY"
        assert body["outcome"] == "FAIL"
        assert body["portrait_allowed"] is False
        portrait = client.post(f"/api/v1/transactions/{tx_id}/portrait")
        assert portrait.status_code == 500
        assert portrait.json()["error"]["code"] == "PORTRAIT_PROCESSING_FAILED"
    store: TransactionFileStore = app.state.transaction_store
    assert not store.artifact_exists(tx_id, "portrait/processed.jpg")


def test_transaction_liveness_gated_when_experiment_disabled(tmp_path) -> None:
    app = _make_app(tmp_path, vlm_experiment_enabled=False)
    with TestClient(app) as client:
        response = client.post("/api/v1/transactions/00000000000000000000000000000000/liveness")
        assert response.status_code == 403
        assert response.json()["error"]["code"] == "VLM_DISABLED"


def test_transaction_liveness_idempotent_single_provider_call(tmp_path, monkeypatch) -> None:
    """A repeated evaluation for the same capture returns the stored result (one provider call)."""
    from app.experiments.vlm import VlmEvaluationService

    calls: list[int] = [0]
    original = VlmEvaluationService.evaluate

    async def counting_evaluate(self, request):
        calls[0] += 1
        return await original(self, request)

    monkeypatch.setattr(VlmEvaluationService, "evaluate", counting_evaluate)

    app = _make_app(tmp_path, vlm_provider="mock", vlm_mock_behavior="live")
    with TestClient(app) as client:
        tx_id = _create_transaction(client)
        first = client.post(f"/api/v1/transactions/{tx_id}/liveness")
        assert first.status_code == 200
        second = client.post(f"/api/v1/transactions/{tx_id}/liveness")
        assert second.status_code == 200
        assert first.json() == second.json()
    assert calls[0] == 1  # second call served from the persisted evaluation
