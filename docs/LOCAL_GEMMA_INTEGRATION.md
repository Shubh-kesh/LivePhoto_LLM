# LivePhoto — Local Gemma Integration (M5.6 §15-20, §23, §65-69)

LivePhoto's UAT VLM experiments use a **self-hosted vision-capable Gemma** served behind an
**OpenAI-compatible Chat Completions API** (e.g. vLLM). Gemma is an independent inference service;
LivePhoto talks to it only through the `LocalVisionProvider` adapter.

## Architecture

```
Frontend (browser)
   │  (multipart JPEG frames — never to Gemma directly)
Backend (LivePhoto)
   │  LocalVisionProvider (OpenAI-compatible adapter)
   │  POST <base>/chat/completions
Gemma inference service (e.g. vLLM, OpenAI-compatible)
```

The frontend never knows `LOCAL_VLM_BASE_URL`. The backend adapter calls
`POST {LOCAL_VLM_BASE_URL}/chat/completions`.

## Configuration

```env
VLM_PROVIDER=local
LOCAL_VLM_BASE_URL=http://gemma-vlm.livephoto.svc.cluster.local:8000/v1
LOCAL_VLM_MODEL=google/gemma-3-12b-it
LOCAL_VLM_API_KEY=<set-at-runtime>
```

LivePhoto then calls:
```
POST http://gemma-vlm.livephoto.svc.cluster.local:8000/v1/chat/completions
```

`LOCAL_VLM_MODEL` is the exact model name the service serves. It is **not hardcoded** anywhere in
application logic (M5.6 §18, §68). The 4B/12B/27B/quantized/fine-tuned choice depends on UAT GPU
resources and benchmark results.

## Required: vision-capable Gemma

**A text-only Gemma deployment cannot perform LivePhoto image evaluation.** The configured
model/server MUST accept image input (image content parts / multimodal). Verify before UAT that
the served model is vision-capable (M5.6 §19).

## Request contract (OpenAI-compatible)

The backend sends a versioned passive-liveness prompt and the captured JPEG frames as inline
data URLs (Base64 exists only as a transient in-memory transport representation — never logged,
persisted, or returned):

```json
{
  "model": "<LOCAL_VLM_MODEL>",
  "messages": [
    { "role": "system", "content": "<versioned passive-liveness prompt>" },
    {
      "role": "user",
      "content": [
        { "type": "text", "text": "<task>" },
        { "type": "image_url", "image_url": { "url": "data:image/jpeg;base64,..." } }
      ]
    }
  ],
  "temperature": 0,
  "max_tokens": 512,
  "response_format": { "type": "json_object" }
}
```

The response is validated strictly against `VlmAssessment` (`vlm-result-v1`); invalid output is a
`SCHEMA_VALIDATION_ERROR`, never silently fixed (M5.6 §22).

## Health / capability check

`LocalVisionProvider.health()` attempts `GET {LOCAL_VLM_BASE_URL}/models` where supported and
returns `ok`/`degraded`/`error`. It never runs at startup and never crashes the app (M5.6 §24).
The base URL is never exposed to the frontend.

Manual smoke (run only when a local inference server actually exists — M5.6 §71):
```bash
curl "$LOCAL_VLM_BASE_URL/models"
```

## No fallback

In UAT a local Gemma failure returns a diagnostic provider error; LivePhoto does **not** fall back
to Gemini/Groq/OpenRouter (M5.6 §25).

## Scope boundary (M5.6 §69)

No Gemma/vLLM **runtime image** is built in this milestone: GPU type/memory, CUDA/runtime, model
size/quantization and weight-distribution method are not yet specified. Only the API integration
seam and documentation are provided. A separate inference-image step can be added after GPU details
are known.
