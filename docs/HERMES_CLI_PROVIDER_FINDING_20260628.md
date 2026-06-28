# Hermes CLI Custom Provider Finding — 2026-06-28

## Summary

The 1min-relay Hermes Safe Mode fork works correctly as a direct OpenAI-compatible relay.

However, using Hermes CLI one-shot mode (`hermes -z`) with `model.provider: custom` is not approved for functional production use, because Hermes injects its own base system prompt and tool context into requests before they reach the relay.

## Confirmed

Direct calls to:

`http://1min-relay:5001/v1/chat/completions`

returned clean functional outputs for summary and rewrite tests.

Hermes CLI calls through:

`hermes -p relaypilot -z ...`

produced functional contamination with Hermes/Nous Research documentation content.

A local capture provider confirmed that Hermes sends a large system prompt containing:

- Hermes Agent identity
- Nous Research references
- Hermes documentation URL
- memory instructions
- tool-use enforcement
- execution discipline instructions
- active profile metadata

The captured request also showed:

- `stream: true`
- `tools_present: true`
- `tool_count: 16`

This occurred even with:

- clean isolated profile
- `toolsets: []`
- `--ignore-rules`
- empty working directory

## Interpretation

The contamination is not caused by 1min.ai and not caused by the relay.

It originates in Hermes CLI request construction / base system prompt / default tool context.

## Gate Result

- Direct Relay Functional: PASS
- Hermes Safe Relay Footer Sanitizer: PASS
- Hermes CLI Custom Provider Echo Tests: PASS
- Hermes CLI Custom Provider Functional Tests: FAIL
- Production migration of ThopCore/ThopAssist/ThopInvest main profiles: NO-GO

## Decision

Do not patch `/opt/hermes` runtime code.

Do not migrate productive Hermes profiles to the relay.

Use the relay only for direct internal worker/service calls unless Hermes provides an official minimal/no-system-prompt mode for custom providers.

## Recommended Path

Create a separate minimal internal worker/client that calls the relay directly for low-risk text tasks such as:

- rewrite
- summarize
- classify
- draft text

This worker must not use Hermes CLI as the model runner.

