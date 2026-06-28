import importlib
import os
import sys
import unittest
from unittest.mock import Mock, patch


SAFE_ENV = {
    "HERMES_SAFE_MODE": "true",
    "ONE_MIN_AI_API_KEY": "test-upstream-key",
    "SUBSET_OF_ONE_MIN_PERMITTED_MODELS": "gpt-4o-mini,gpt-4o,gpt-5.4-mini,mistral-nemo",
    "DEFAULT_MODEL": "gpt-4o-mini",
    "PORT": "5019",
}


def load_main(extra_env=None):
    env = SAFE_ENV.copy()
    if extra_env:
        env.update(extra_env)
    for key in [
        "HERMES_SAFE_MODE",
        "ONE_MIN_AI_API_KEY",
        "SUBSET_OF_ONE_MIN_PERMITTED_MODELS",
        "DEFAULT_MODEL",
        "PORT",
        "FORCE_NON_STREAMING",
        "SYNTHETIC_SSE_WHEN_STREAM_REQUESTED",
        "DISABLE_1MIN_WEB_SEARCH",
        "DISABLE_1MIN_MEMORIES",
        "DISABLE_1MIN_HISTORY",
        "STATIC_MODELS_ONLY",
        "PERMIT_MODELS_FROM_SUBSET_ONLY",
        "ALLOW_CLIENT_API_KEY_FALLBACK",
    ]:
        os.environ.pop(key, None)
    os.environ.update(env)
    sys.modules.pop("main", None)
    import main
    return importlib.reload(main)


class FakeResponse:
    def __init__(self, status_code=200, payload=None, text=""):
        self.status_code = status_code
        self._payload = payload or {}
        self.text = text

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError("upstream error")


def ai_payload(text="Final answer"):
    return {"aiRecord": {"aiRecordDetail": {"resultObject": [text]}}}


class HermesSafeTests(unittest.TestCase):
    def test_models_returns_static_allowed_models(self):
        main = load_main()
        client = main.app.test_client()

        resp = client.get("/v1/models")

        self.assertEqual(resp.status_code, 200)
        ids = [item["id"] for item in resp.get_json()["data"]]
        self.assertEqual(ids, ["gpt-4o-mini", "gpt-4o", "gpt-5.4-mini", "mistral-nemo"])

    def test_model_not_allowed_blocks_before_upstream(self):
        main = load_main()
        client = main.app.test_client()
        with patch.object(main.requests, "post") as post:
            resp = client.post("/v1/chat/completions", json={"model": "not-allowed", "messages": [{"role": "user", "content": "hi"}]})

        self.assertEqual(resp.status_code, 400)
        self.assertEqual(resp.get_json()["error"]["code"], "model_not_allowed")
        post.assert_not_called()

    def test_non_stream_chat_uses_non_streaming_url(self):
        main = load_main()
        client = main.app.test_client()
        fake = FakeResponse(payload=ai_payload())
        with patch.object(main.requests, "post", return_value=fake) as post:
            resp = client.post("/v1/chat/completions", json={"model": "gpt-4o-mini", "messages": [{"role": "user", "content": "hi"}]})

        self.assertEqual(resp.status_code, 200)
        self.assertEqual(post.call_args.args[0], main.CHAT_URL)
        self.assertNotEqual(post.call_args.args[0], main.STREAM_URL)

    def test_stream_true_force_non_streaming_does_not_call_streaming_url(self):
        main = load_main()
        client = main.app.test_client()
        fake = FakeResponse(payload=ai_payload())
        with patch.object(main.requests, "post", return_value=fake) as post:
            resp = client.post("/v1/chat/completions", json={"stream": True, "model": "gpt-4o-mini", "messages": [{"role": "user", "content": "hi"}]})

        self.assertEqual(resp.status_code, 200)
        self.assertEqual(post.call_args.args[0], main.CHAT_URL)
        self.assertNotIn("isStreaming=true", post.call_args.args[0])

    def test_stream_true_synthetic_sse_returns_openai_sse_and_done(self):
        main = load_main()
        client = main.app.test_client()
        fake = FakeResponse(payload=ai_payload("Safe final"))
        with patch.object(main.requests, "post", return_value=fake):
            resp = client.post("/v1/chat/completions", json={"stream": True, "model": "gpt-4o-mini", "messages": [{"role": "user", "content": "hi"}]})

        body = resp.get_data(as_text=True)
        self.assertEqual(resp.status_code, 200)
        self.assertIn("text/event-stream", resp.content_type)
        self.assertIn('"object": "chat.completion.chunk"', body)
        self.assertIn("Safe final", body)
        self.assertTrue(body.rstrip().endswith("data: [DONE]"))

    def test_link_context_clean_output_unchanged(self):
        main = load_main()
        client = main.app.test_client()
        fake = FakeResponse(payload=ai_payload("Clean assistant output"))
        with patch.object(main.requests, "post", return_value=fake):
            resp = client.post("/v1/chat/completions", json={"model": "gpt-4o-mini", "messages": [{"role": "user", "content": "hi"}]})

        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.get_json()["choices"][0]["message"]["content"], "Clean assistant output")

    def test_link_context_suffix_with_newline_removed(self):
        main = load_main()
        client = main.app.test_client()
        leaked = "Final answer\nHere is some information from the links you provided:"
        fake = FakeResponse(payload=ai_payload(leaked))
        with patch.object(main.requests, "post", return_value=fake):
            resp = client.post("/v1/chat/completions", json={"model": "gpt-4o-mini", "messages": [{"role": "user", "content": "hi"}]})

        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.get_json()["choices"][0]["message"]["content"], "Final answer")

    def test_link_context_suffix_without_newline_removed(self):
        main = load_main()
        client = main.app.test_client()
        leaked = "relayclean_post_memory_works_1Here is some information from the links you provided:"
        fake = FakeResponse(payload=ai_payload(leaked))
        with patch.object(main.requests, "post", return_value=fake):
            resp = client.post("/v1/chat/completions", json={"model": "gpt-4o-mini", "messages": [{"role": "user", "content": "hi"}]})

        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.get_json()["choices"][0]["message"]["content"], "relayclean_post_memory_works_1")

    def test_link_context_suffix_with_url_removed(self):
        main = load_main()
        client = main.app.test_client()
        leaked = "Final answer\nHere is some information from the links you provided: Link: https://hermes-agent.nousresearch.com/docs"
        fake = FakeResponse(payload=ai_payload(leaked))
        with patch.object(main.requests, "post", return_value=fake):
            resp = client.post("/v1/chat/completions", json={"model": "gpt-4o-mini", "messages": [{"role": "user", "content": "hi"}]})

        self.assertEqual(resp.status_code, 200)
        content = resp.get_json()["choices"][0]["message"]["content"]
        self.assertEqual(content, "Final answer")
        self.assertNotIn("hermes-agent.nousresearch.com", content)

    def test_link_context_suffix_only_is_blocked(self):
        main = load_main()
        client = main.app.test_client()
        leaked = "Here is some information from the links you provided: Link: https://hermes-agent.nousresearch.com/docs"
        fake = FakeResponse(payload=ai_payload(leaked))
        with patch.object(main.requests, "post", return_value=fake):
            resp = client.post("/v1/chat/completions", json={"model": "gpt-4o-mini", "messages": [{"role": "user", "content": "hi"}]})

        body = resp.get_json()
        self.assertEqual(resp.status_code, 502)
        self.assertEqual(body["error"]["type"], "upstream_output_safety_error")
        self.assertEqual(body["error"]["code"], "unsafe_reasoning_leak")
        self.assertNotIn("hermes-agent.nousresearch.com", str(body))

    def test_synthetic_sse_uses_sanitized_link_context_text(self):
        main = load_main()
        client = main.app.test_client()
        leaked = "Stream-safe answerHere is some information from the links you provided: Link: https://hermes-agent.nousresearch.com/docs"
        fake = FakeResponse(payload=ai_payload(leaked))
        with patch.object(main.requests, "post", return_value=fake):
            resp = client.post("/v1/chat/completions", json={"stream": True, "model": "gpt-4o-mini", "messages": [{"role": "user", "content": "hi"}]})

        body = resp.get_data(as_text=True)
        self.assertEqual(resp.status_code, 200)
        self.assertIn("text/event-stream", resp.content_type)
        self.assertIn("Stream-safe answer", body)
        self.assertNotIn("Here is some information from the links you provided", body)
        self.assertNotIn("hermes-agent.nousresearch.com", body)
        self.assertTrue(body.rstrip().endswith("data: [DONE]"))

    def test_upstream_payload_forces_safe_settings_and_omits_conversation_id(self):
        main = load_main()
        client = main.app.test_client()
        fake = FakeResponse(payload=ai_payload())
        with patch.object(main.requests, "post", return_value=fake) as post:
            resp = client.post("/v1/chat/completions", json={"model": "gpt-4o-mini", "messages": [{"role": "user", "content": "hi"}]})

        self.assertEqual(resp.status_code, 200)
        payload = post.call_args.kwargs["json"]
        settings = payload["promptObject"]["settings"]
        self.assertEqual(settings["webSearchSettings"], {"webSearch": False, "numOfSite": 0, "maxWord": 0})
        self.assertFalse(settings["withMemories"])
        self.assertEqual(settings["historySettings"], {"isMixed": False, "historyMessageLimit": 0})
        self.assertNotIn("conversationId", str(payload))

    def test_reasoning_leak_is_blocked(self):
        main = load_main()
        client = main.app.test_client()
        fake = FakeResponse(payload=ai_payload("Considering response to user: hidden planning"))
        with patch.object(main.requests, "post", return_value=fake):
            resp = client.post("/v1/chat/completions", json={"model": "gpt-4o-mini", "messages": [{"role": "user", "content": "hi"}]})

        body = resp.get_json()
        self.assertEqual(resp.status_code, 502)
        self.assertEqual(body["error"]["code"], "unsafe_reasoning_leak")
        self.assertNotIn("hidden planning", str(body))

    def test_upstream_error_does_not_expose_raw_body(self):
        main = load_main()
        client = main.app.test_client()
        fake = FakeResponse(status_code=500, payload={"message": "raw provider secret payload"}, text="raw provider secret payload")
        with patch.object(main.requests, "post", return_value=fake):
            resp = client.post("/v1/chat/completions", json={"model": "gpt-4o-mini", "messages": [{"role": "user", "content": "hi"}]})

        body = resp.get_json()
        self.assertEqual(resp.status_code, 502)
        self.assertEqual(body["error"]["code"], "upstream_error")
        self.assertNotIn("raw provider secret payload", str(body))

    def test_image_route_disabled_in_hermes_safe_mode(self):
        main = load_main()
        client = main.app.test_client()
        resp = client.post("/v1/images/generations", json={"prompt": "x"})

        self.assertEqual(resp.status_code, 400)
        self.assertEqual(resp.get_json()["error"]["code"], "unsupported_in_hermes_safe_mode")

    def test_run_server_uses_port_env(self):
        main = load_main({"PORT": "5099"})
        with patch.object(main.socket, "gethostbyname", return_value="127.0.0.1"), patch.object(main.socket, "gethostname", return_value="localhost"), patch.object(main, "serve") as serve:
            main.run_server()

        serve.assert_called_once()
        self.assertEqual(serve.call_args.kwargs["port"], 5099)


if __name__ == "__main__":
    unittest.main()
