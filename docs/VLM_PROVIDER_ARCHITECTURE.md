# LivePhoto — VLM Provider Architecture (M4)

Status: M4 baseline. Documented per M4 §133.

## Provider interface

`backend/app/providers/vision/contracts.py` defines `VisionProvider`:

```python
class VisionProvider(Protocol):
    @property
    def info(self) -> VisionProviderInfo: ...          # provider_name, model_id, adapter version
    @property
    def capabilities(self) -> VisionProviderCapabilities: ...  # image/bytes limits, structured output
    async def evaluate(self, request: VisionEvaluationRequest) -> VisionEvaluationResponse: ...
    async def health(self) -> ProviderHealth: ...
```

Business workflows depend only on this interface. A future self-hosted provider
(`LocalVisionProvider`) uses the same `VisionEvaluationRequest/Response` (M4 §162).

## Implementations

- **Gemini** — `gemini_provider.py`, official `google-genai` SDK, `response_schema` structured
  output, inline images.
- **OpenRouter** — `openrouter_provider.py`, OpenAI-compatible chat completions over `httpx`,
  inline data-URL images. Provider = `openrouter`; the actual model id is always recorded (M4 §102).
- **Groq** — `groq_provider.py`, same OpenAI-compatible transport.
- **Mock** — `mock_provider.py`, deterministic responses for tests/E2E (no network).
- Registry: `registry.py` builds the requested provider from settings; real providers require a
  configured key + model; `mock` is always available.

## Configuration

Server-side settings (`backend/app/core/config.py` + `.env.example`):

```
VLM_EXPERIMENT_ENABLED
VLM_PROVIDER
VLM_TIMEOUT_SECONDS
VLM_MAX_RETRIES
VLM_MAX_FRAMES
VLM_MAX_SINGLE_IMAGE_BYTES
VLM_MAX_TOTAL_IMAGE_BYTES
GEMINI_API_KEY / GEMINI_MODEL
GROQ_API_KEY / GROQ_MODEL
OPENROUTER_API_KEY / OPENROUTER_MODEL
```

API keys are `SecretStr`. Model IDs are configuration-driven, never hardcoded model identities.

## Timeouts & retries

- Every provider call has an explicit timeout (`VLM_TIMEOUT_SECONDS`).
- Conservative retries (`VLM_MAX_RETRIES`, default 1) on transient failures only: 429, selected
  5xx, network reset/timeout. Authentication, bad-request and our-own schema errors are never
  retried (M4 §31).
- No automatic provider fallback during benchmarks — a failed run returns `PROVIDER_ERROR` (M4 §32).

## Structured outputs

- `VlmAssessment` (schema `vlm-result-v1`) is strict Pydantic (`extra="forbid"`, bounded confidence,
  finite enums). Invalid provider output → `SCHEMA_VALIDATION_ERROR` (never silently fixed).
- Gemini uses `response_schema`; OpenRouter/Groq use `response_format: json_object`. All parsing
  goes through `parse_assessment`; provider-native JSON never reaches the frontend.

## Image transport & privacy

- Browser → backend: **multipart/form-data**, bounded (M4 §12, §15, §70-72). No JSON Base64.
- Provider inline Base64 is temporary backend transport only — converted, sent, released; never
  stored/logged/persisted (M4 §13).
- No provider file-storage APIs by default (M4 §14).
- Raw images and raw provider outputs are never logged (M4 §59-61).

## Error mapping (fail-closed)

Provider-independent taxonomy in `errors.py` (M4 §62): `VLM_DISABLED`, `PROVIDER_NOT_CONFIGURED`,
`PROVIDER_AUTH_ERROR`, `PROVIDER_TIMEOUT`, `PROVIDER_RATE_LIMITED`, `PROVIDER_UNAVAILABLE`,
`PROVIDER_BAD_REQUEST`, `REQUEST_TOO_LARGE`, `TOO_MANY_IMAGES`, `UNSUPPORTED_MEDIA_TYPE`,
`SCHEMA_VALIDATION_ERROR`, `PROVIDER_RESPONSE_ERROR`, `UNKNOWN_PROVIDER_ERROR`. A provider failure
never becomes `LIVE` (M4 §63).

## Observability

Low-cardinality Prometheus metrics (`livephoto_vlm_*`): requests by provider+result, duration by
provider, errors by provider+error_type. No transaction/capture/sample IDs in labels (M4 §125-126).
Safe structured log event `vlm_evaluation_completed` (provider, model, prompt_version, image_count,
classification, latency_ms, request_id) — no image content (M4 §127).

## Endpoint guard

`POST/GET /api/v1/experiments/vlm/*` operate only when `VLM_EXPERIMENT_ENABLED=true` **and**
`APP_ENV` is not `uat`/`production` (M4 §10-11).