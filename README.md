# 1min-Relay

## Overview
1min-Relay relays the 1min AI API to an OpenAI-compatible structure in under one minute. This project supports fast, reliable integration with various clients, features for managing conversation history and models, and optional hosted or self-hosted deployments. For details and updates, visit the hosted version and community channels below.

## Key links
- Hosted version: https://www.kokodev.cc/1minrelay
- Discord for support and updates: https://discord.gg/GQd3DrxXyj
- Donation: https://donate.stripe.com/00w4gB1NbdI60afcKPgMw00
- Paid hosted version and perks: https://shop.kokodev.cc/products
- GitHub repository: https://github.com/kokofixcomputers/1min-relay

## Features
- bolt.diy compatibility: Seamless integration with bolt.diy
- Conversation history: Preserve and manage conversations
- Broad client compatibility: Works with most clients that support an OpenAI Custom Endpoint
- Fast and reliable relay: Relays 1min AI API to an OpenAI-compatible structure quickly
- User-friendly: Easy to install and use
- Model exposure control: Expose all models or a predefined subset
- Streaming support: Real-time streaming for faster interactions
- Non-streaming support: Compatible with non-streaming workflows
- Docker support: Simple deployment with Docker
- Multi-document support: Upload and process documents (e.g., .docx, .pdf, .txt, .yaml, etc.)
- Image support: Upload and process images
- Architecture compatibility: ARM64 and AMD64 support
- Concurrent requests: Handles multiple requests simultaneously

## Paid perks (optional)
- Hosted service: Access anytime, anywhere
- Latest features: Early access to features not yet in the public version (e.g., image generation)
- Priority bug fixes: Faster resolution of common issues
- Priority support: Faster assistance compared to the public version

## Installation

### Bare-metal (local machine)
- Prerequisites: Python 3.x, pip, Git
- Clone the repository:
  - git clone https://github.com/kokofixcomputers/1min-relay.git
- Install dependencies:
  - pip install -r requirements.txt
- Run:
  - python3 main.py
  Note: On some systems, you may need to use python instead of python3.

### Docker (recommended for ease of deployment)

Pre-built images
- Pull the image:
  - docker pull kokofixcomputers/1min-relay:latest
- Create a dedicated network (recommended for memcached communication):
  - docker network create 1min-relay-network
- Start Memcached:
  - docker run -d --name memcached --network 1min-relay-network memcached
- Run the 1min-relay container:
  - docker run -d --name 1min-relay-container --network 1min-relay-network -p 5001:5001 \
    -e SUBSET_OF_ONE_MIN_PERMITTED_MODELS="mistral-nemo,gpt-4o-mini,deepseek-chat" \
    -e PERMIT_MODELS_FROM_SUBSET_ONLY=True \
    kokofixcomputers/1min-relay:latest

Environment variables
- SUBSET_OF_ONE_MIN_PERMITTED_MODELS: Subset of 1min.ai models to expose. Default: mistral-nemo,gpt-4o,deepseek-chat.
- PERMIT_MODELS_FROM_SUBSET_ONLY: Restrict model usage to the specified subset. Set to True to enforce, False to allow all models supported by 1min.ai. Default: True.
- HOST: Host to expose HTTP server at. Default: '0.0.0.0'
- PORT: Port to expose HTTP server at. Default: 5001

Self-build (Docker image from source)
1) Build the Docker image:
   - docker build -t 1min-relay:latest .
2) Create a dedicated network:
   - docker network create 1min-relay-network
3) Run Memcached:
   - docker run -d --name memcached --network 1min-relay-network memcached
4) Run the 1min-relay container:
   - docker run -d --name 1min-relay-container --network 1min-relay-network -p 5001:5001 \
     -e SUBSET_OF_ONE_MIN_PERMITTED_MODELS="mistral-nemo,gpt-4o-mini,deepseek-chat" \
     -e PERMIT_MODELS_FROM_SUBSET_ONLY=True \
     1min-relay:latest

Notes
- The container port 5001 is exposed to the host for API access.
- When using Docker Compose, you can simplify networking and service orchestration (see repository for a provided compose file).

Verification
- Check container logs:
  - docker logs -f 1min-relay-container
- Test the API endpoint (example):
  - curl -X GET http://localhost:5001/v1/models

### If you find this project useful, please consider starring the repository and supporting us through the provided donation or paid hosted options.

## Hermes Safe Mode

Hermes Safe Mode is a chat-only operating mode for using this relay behind Hermes Agent without exposing provider metadata, internal planning text, web-search chatter, conversation memory, or raw upstream payloads through OpenAI-compatible responses.

Enable it with:

```bash
HERMES_SAFE_MODE=true
ONE_MIN_AI_API_KEY=replace-with-runtime-secret
```

Do not commit real API keys or runtime secrets to Git. Provide `ONE_MIN_AI_API_KEY` only through your runtime environment or secret manager.

### Safe defaults

When `HERMES_SAFE_MODE=true`, these options default to `true` unless explicitly set otherwise:

- `FORCE_NON_STREAMING`
- `SYNTHETIC_SSE_WHEN_STREAM_REQUESTED`
- `DISABLE_1MIN_WEB_SEARCH`
- `DISABLE_1MIN_MEMORIES`
- `DISABLE_1MIN_HISTORY`
- `STATIC_MODELS_ONLY`
- `SUPPRESS_UPSTREAM_METADATA`
- `SANITIZE_ASSISTANT_OUTPUT`
- `BLOCK_REASONING_LEAKS`
- `PERMIT_MODELS_FROM_SUBSET_ONLY`

Default allowed models in Safe Mode:

```text
gpt-4o-mini,gpt-4o,gpt-5.4-mini,mistral-nemo
```

Default model in Safe Mode:

```text
gpt-4o-mini
```

### Environment variables

Supported Safe Mode variables:

- `ONE_MIN_AI_API_KEY`: upstream 1min.ai API key supplied by runtime environment.
- `HOST`: bind host. Default: `0.0.0.0`.
- `PORT`: bind port. Default: `5001`.
- `HERMES_SAFE_MODE`: enables Hermes-safe defaults.
- `FORCE_NON_STREAMING`: never call the native 1min.ai streaming URL.
- `SYNTHETIC_SSE_WHEN_STREAM_REQUESTED`: return synthetic OpenAI-compatible SSE when clients request `stream=true`.
- `DISABLE_1MIN_WEB_SEARCH`: forces `webSearch=false`, `numOfSite=0`, `maxWord=0`.
- `DISABLE_1MIN_MEMORIES`: forces `withMemories=false` and omits conversation IDs.
- `DISABLE_1MIN_HISTORY`: forces `isMixed=false` and `historyMessageLimit=0`.
- `STATIC_MODELS_ONLY`: returns only local static model metadata from the allowed subset.
- `SUPPRESS_UPSTREAM_METADATA`: suppresses raw upstream metadata from responses.
- `SANITIZE_ASSISTANT_OUTPUT`: returns only final assistant content.
- `BLOCK_REASONING_LEAKS`: blocks unsafe reasoning, planning, tool/debug, provider, and raw `aiRecord` leakage.
- `SUBSET_OF_ONE_MIN_PERMITTED_MODELS`: comma-separated model allowlist.
- `PERMIT_MODELS_FROM_SUBSET_ONLY`: blocks non-allowlisted models before upstream calls.
- `DEFAULT_MODEL`: model used when the client omits `model`.
- `MAX_PROMPT_CHARS`: optional flattened prompt length cap. `0` means no cap.
- `REQUEST_TIMEOUT_SECONDS`: upstream request timeout. Default: `120`.
- `LOG_PROMPTS`: default `false`; do not enable in Hermes production contexts.
- `LOG_RESPONSES`: default `false`; do not enable in Hermes production contexts.
- `LOG_SECRETS`: default `false`; the app still redacts secret-like logging fields.
- `ALLOW_CLIENT_API_KEY_FALLBACK`: default `false`; only forwards client bearer tokens upstream when explicitly enabled.

### Docker Compose example

```yaml
services:
  1min-relay:
    image: kokofixcomputers/1min-relay:latest
    ports:
      - "5001:5001"
    environment:
      - HERMES_SAFE_MODE=true
      - ONE_MIN_AI_API_KEY=${ONE_MIN_AI_API_KEY}
      - HOST=0.0.0.0
      - PORT=5001
      - SUBSET_OF_ONE_MIN_PERMITTED_MODELS=gpt-4o-mini,gpt-4o,gpt-5.4-mini,mistral-nemo
      - DEFAULT_MODEL=gpt-4o-mini
      - LOG_PROMPTS=false
      - LOG_RESPONSES=false
      - LOG_SECRETS=false
```

### Safe Mode limitations

Phase 1 is chat only. In `HERMES_SAFE_MODE=true`, `/v1/images/generations` returns an OpenAI-compatible `unsupported_in_hermes_safe_mode` error. Vision attachments are not sent upstream in Safe Mode.

Native upstream streaming is disabled by default in Safe Mode. If a client requests `stream=true`, the relay calls 1min.ai non-streaming, sanitizes the final text, and emits synthetic OpenAI-compatible SSE chunks ending with `data: [DONE]`.

### Hermes isolated test plan

Run only local tests with mocks. Do not use real API keys and do not call Hermes runtime, Telegram, broker, trading, investment, Portainer, Docker runtime containers, `/srv/stacks`, `/srv/runtime`, or `/srv/secrets`.

```bash
python3 -m py_compile main.py
python3 -m unittest discover -s tests -v
```

