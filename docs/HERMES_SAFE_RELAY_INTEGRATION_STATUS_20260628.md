# Hermes Safe Relay Integration Status — 2026-06-28

## Scope

This document records the current validation state of the `1min-relay-hermes-safe` fork for use as an internal OpenAI-compatible relay for Hermes Agent.

## Current Result

Status: PASS for isolated relay and isolated Hermes test profiles.

Not approved for broad production migration yet.

## Validated

- Fork built successfully.
- Hermes Safe Mode implemented.
- `/v1/models` returns static allowlisted models only.
- `/v1/chat/completions` supports OpenAI-compatible non-streaming JSON.
- `stream=true` is handled through synthetic OpenAI-compatible SSE.
- Upstream 1min.ai calls are forced non-streaming in Safe Mode.
- Image generation route is disabled in Safe Mode.
- Model allowlist blocks disallowed models before upstream calls.
- Logs do not expose prompts, client Authorization headers, API keys, or raw upstream payloads.
- Relay runs only internally in the Hermes Docker network via `expose: 5001`.
- No public host port is published.
- `hermes-agent` can reach `http://1min-relay:5001/v1`.
- `relayclean` and `relaypilot` custom provider tests passed after sanitizer patch.
- Link-context leakage sanitizer removes the known Hermes footer:
  `Here is some information from the links you provided`.

## Tests Passed

- Python compile check: PASS.
- Unit tests: 16 tests PASS.
- Direct Relay 10/10: PASS.
- Hermes `relayclean` sanitized 20/20: PASS.
- Hermes `relaypilot` 30/30: PASS.

## Safety Boundaries

No migration performed for:

- thopcore main profile
- thopassistant main profile
- thopinvest main profile
- productive gateways
- cronjobs
- Telegram-facing production agents

## Current Approved Usage

Approved only for isolated low-risk test profiles:

- `relayclean`
- `relaypilot`

## Next Gate

Gate I.8 may validate a low-risk functional profile for simple text generation/summarization with:

- no gateway
- no tools
- no cron
- no production data
- no broker/trading data
- no host admin tasks

