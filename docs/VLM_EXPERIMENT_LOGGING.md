# LivePhoto — VLM Experiment Logging (M5.6 §27-36)

Structured, privacy-safe diagnostics for VLM experiment requests and responses, gated by
`VLM_EXPERIMENT_LOGGING_ENABLED` (default `false`). Logs are JSON to stdout/stderr (container
friendly); no rotating local log files are designed inside containers (M5.6 §35).

## Events

- `vlm_experiment_request_started` — before the provider call.
- `vlm_experiment_response_received` — on a normalized success.
- `vlm_experiment_failed` — on a provider/validation error.

Correlation: every event carries the same `experiment_id` (per evaluation) and the HTTP
`request_id` (bound by request middleware). Correlation never uses customer PII (M5.6 §36).

## Request log fields (§28)

`request_id`, `experiment_id`, `environment`, `provider`, `model`,
`provider_adapter_version`, `prompt_id`, `prompt_version`, `schema_version`, `frame_strategy`,
`image_count`, `image_sizes_bytes`, `total_image_bytes`, `mime_types`,
`capture_config_version`, `quality_config_version`, `timestamp`.
**Image content is never logged.**

## Response log fields (§29)

`request_id`, `experiment_id`, `provider`, `model`, `classification`, `attack_medium`,
`self_reported_confidence`, `evidence_codes`, `provider_latency_ms`, `total_latency_ms`,
`input_tokens`, `output_tokens`, `total_tokens`, `schema_validation: "success"`.

The normalized `VlmAssessment` is logged by default, not uncontrolled raw model text (M5.6 §32).

## Error log fields (§30)

`request_id`, `experiment_id`, `provider`, `model`, `error_code`, `retry_count`, `latency_ms`.
Raw exceptions that could contain credentials/request bodies are not logged.

## Raw local model text (§33-34)

Optional, off by default: `VLM_EXPERIMENT_LOG_RAW_MODEL_TEXT=false`.

When `true`, it is allowed **only** for `provider = local` and never in `production`. Raw text is
truncated to **8192 characters** and secret patterns (`api_key`, `Bearer`, `sk-…`) are masked
before logging. Request images and provider credentials are never included.

## Never logged (§31)

JPEG bytes, multipart body, Base64, data URLs, Blob data, `Authorization`, API keys,
`LOCAL_VLM_API_KEY`, raw customer images, device IDs. The structlog redaction processor also masks
any key whose name matches token/secret/password/api_key families as a safety net.
