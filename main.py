import base64
import json
import logging
import os
import socket
import time
import uuid
import warnings
from io import BytesIO

try:
    import coloredlogs
except ImportError:
    coloredlogs = None
import requests
try:
    import tiktoken
except ImportError:
    tiktoken = None
from flask import Flask, Response, jsonify, make_response, request
try:
    from flask_limiter import Limiter
    from flask_limiter.util import get_remote_address
except ImportError:
    Limiter = None

    def get_remote_address():
        return request.remote_addr or "127.0.0.1"
try:
    from pymemcache.client.base import Client
except ImportError:
    Client = None
try:
    from waitress import serve
except ImportError:
    def serve(app, host="0.0.0.0", port=5001):
        app.run(host=host, port=port)
try:
    from mistral_common.protocol.instruct.messages import UserMessage
    from mistral_common.protocol.instruct.request import ChatCompletionRequest
    from mistral_common.tokens.tokenizers.mistral import MistralTokenizer
except ImportError:
    UserMessage = None
    ChatCompletionRequest = None
    MistralTokenizer = None

try:
    import printedcolors
except Exception:
    class _Color:
        class fg:
            lightcyan = ""
        reset = ""
    printedcolors = type("printedcolors", (), {"Color": _Color})()

warnings.filterwarnings("ignore", category=UserWarning, module="flask_limiter.extension")

logger = logging.getLogger("relay")
if coloredlogs is not None:
    coloredlogs.install(level=os.getenv("LOG_LEVEL", "INFO"), logger=logger)
else:
    logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))


def env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "t", "yes", "y", "on"}


def env_int(name: str, default: int, minimum: int | None = None) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        value = int(raw.strip())
    except (TypeError, ValueError):
        return default
    if minimum is not None and value < minimum:
        return default
    return value


def env_csv(name: str, default: str) -> list[str]:
    raw = os.getenv(name, default)
    seen = set()
    values = []
    for item in raw.split(","):
        value = item.strip()
        if value and value not in seen:
            values.append(value)
            seen.add(value)
    return values


APP_NAME = os.getenv("APP_NAME", "relay")
HOST = os.getenv("HOST", os.getenv("APP_HOST", "0.0.0.0"))
PORT = env_int("PORT", env_int("APP_PORT", 5001), minimum=1)

HERMES_SAFE_MODE = env_bool("HERMES_SAFE_MODE", False)
FORCE_NON_STREAMING = env_bool("FORCE_NON_STREAMING", HERMES_SAFE_MODE)
SYNTHETIC_SSE_WHEN_STREAM_REQUESTED = env_bool("SYNTHETIC_SSE_WHEN_STREAM_REQUESTED", HERMES_SAFE_MODE)
DISABLE_1MIN_WEB_SEARCH = env_bool("DISABLE_1MIN_WEB_SEARCH", HERMES_SAFE_MODE)
DISABLE_1MIN_MEMORIES = env_bool("DISABLE_1MIN_MEMORIES", HERMES_SAFE_MODE)
DISABLE_1MIN_HISTORY = env_bool("DISABLE_1MIN_HISTORY", HERMES_SAFE_MODE)
STATIC_MODELS_ONLY = env_bool("STATIC_MODELS_ONLY", HERMES_SAFE_MODE)
SUPPRESS_UPSTREAM_METADATA = env_bool("SUPPRESS_UPSTREAM_METADATA", HERMES_SAFE_MODE)
SANITIZE_ASSISTANT_OUTPUT = env_bool("SANITIZE_ASSISTANT_OUTPUT", HERMES_SAFE_MODE)
BLOCK_REASONING_LEAKS = env_bool("BLOCK_REASONING_LEAKS", HERMES_SAFE_MODE)
PERMIT_MODELS_FROM_SUBSET_ONLY = env_bool("PERMIT_MODELS_FROM_SUBSET_ONLY", HERMES_SAFE_MODE)
MAX_PROMPT_CHARS = env_int("MAX_PROMPT_CHARS", 0, minimum=0)
REQUEST_TIMEOUT_SECONDS = env_int("REQUEST_TIMEOUT_SECONDS", 120, minimum=1)
LOG_PROMPTS = env_bool("LOG_PROMPTS", False)
LOG_RESPONSES = env_bool("LOG_RESPONSES", False)
LOG_SECRETS = env_bool("LOG_SECRETS", False)
ALLOW_CLIENT_API_KEY_FALLBACK = env_bool("ALLOW_CLIENT_API_KEY_FALLBACK", False)
ONE_MIN_AI_API_KEY = os.getenv("ONE_MIN_AI_API_KEY", "").strip()
DEFAULT_ALLOWED_MODELS = "gpt-4o-mini,gpt-4o,gpt-5.4-mini,mistral-nemo"
DEFAULT_MODEL = os.getenv("DEFAULT_MODEL", "gpt-4o-mini" if HERMES_SAFE_MODE else "mistral-nemo").strip()

API_BASE = os.getenv("ONE_MIN_API_BASE", "https://api.1min.ai/api")
CHAT_URL = os.getenv("ONE_MIN_CHAT_API_URL", f"{API_BASE}/chat-with-ai")
FEATURES_URL = os.getenv("ONE_MIN_API_URL", f"{API_BASE}/features")
CONV_URL = os.getenv("ONE_MIN_CONVERSATION_API_URL", f"{API_BASE}/conversations")
STREAM_URL = os.getenv(
    "ONE_MIN_CONVERSATION_API_STREAMING_URL",
    f"{API_BASE}/chat-with-ai?isStreaming=true",
)
ASSET_URL = os.getenv("ONE_MIN_ASSET_URL", f"{API_BASE}/assets")

OLD_MODEL_LIST = [
    "gpt-5-nano",
    "gpt-5",
    "gpt-5-mini",
    "o3-mini",
    "deepseek-chat",
    "deepseek-reasoner",
    "o1-preview",
    "o1-mini",
    "gpt-4o-mini",
    "gpt-4o",
    "gpt-4-turbo",
    "gpt-4",
    "gpt-3.5-turbo",
    "claude-instant-1.2",
    "claude-2.1",
    "claude-3-7-sonnet-20250219",
    "claude-3-5-sonnet-20240620",
    "claude-3-opus-20240229",
    "claude-3-sonnet-20240229",
    "claude-3-haiku-20240307",
    "gemini-1.0-pro",
    "gemini-1.5-pro",
    "gemini-1.5-flash",
    "mistral-large-latest",
    "mistral-small-latest",
    "mistral-nemo",
    "open-mistral-7b",
    "gpt-o1-pro",
    "gpt-o4-mini",
    "gpt-4.1-nano",
    "gpt-4.1-mini",
    "meta/llama-2-70b-chat",
    "meta/meta-llama-3-70b-instruct",
    "meta/meta-llama-3.1-405b-instruct",
    "command",
]

VISION_MODELS = {"gpt-4o", "gpt-4o-mini", "gpt-4-turbo"}

IMAGE_MODELS = {
    "stable-image",
    "stable-diffusion-xl-1024-v1-0",
    "stable-diffusion-v1-6",
    "esrgan-v1-x2plus",
    "clipdrop",
    "midjourney",
    "midjourney_6_1",
    "6b645e3a-d64f-4341-a6d8-7a3690fbf042",
    "b24e16ff-06e3-43eb-8d33-4416c2d75876",
    "e71a1c2f-4f80-4800-934f-2c68979d8cc8",
    "1e60896f-3c26-4296-8ecc-53e2afecc132",
    "aa77f04e-3eec-4034-9c07-d0f619684628",
    "2067ae52-33fd-4a82-bb92-c2c55e7d2786",
    "black-forest-labs/flux-schnell",
}

MODEL_SUBSET = env_csv(
    "SUBSET_OF_ONE_MIN_PERMITTED_MODELS",
    DEFAULT_ALLOWED_MODELS if HERMES_SAFE_MODE else "mistral-nemo,gpt-4o,deepseek-chat",
)
STRICT_MODELS = PERMIT_MODELS_FROM_SUBSET_ONLY
MODELS = MODEL_SUBSET if (STRICT_MODELS or STATIC_MODELS_ONLY) else OLD_MODEL_LIST

MEM_HOST = os.getenv("MEMCACHED_HOST", os.getenv("MEM_HOST", "memcached"))
MEM_PORT = env_int("MEMCACHED_PORT", env_int("MEM_PORT", 11211), minimum=1)

app = Flask(__name__)


def safe_log(level: int, event: str, **fields):
    safe_fields = {}
    for key, value in fields.items():
        lowered = key.lower()
        if any(token in lowered for token in ("key", "secret", "authorization", "prompt", "response", "airecord", "payload")):
            safe_fields[key] = "[redacted]"
        elif isinstance(value, str) and len(value) > 120:
            safe_fields[key] = value[:117] + "..."
        else:
            safe_fields[key] = value
    logger.log(level, "%s %s", event, safe_fields if safe_fields else "")


def memcached_ok(host: str = MEM_HOST, port: int = MEM_PORT) -> bool:
    if Client is None:
        return False
    try:
        c = Client((host, port), connect_timeout=0.2, timeout=0.2)
        c.set("relay_test", b"1")
        ok = c.get("relay_test") == b"1"
        c.delete("relay_test")
        return ok
    except Exception:
        return False


class _NoopLimiter:
    def limit(self, _rule):
        def decorator(func):
            return func
        return decorator


if Limiter is None:
    limiter = _NoopLimiter()
elif memcached_ok():
    limiter = Limiter(get_remote_address, app=app, storage_uri=f"memcached://{MEM_HOST}:{MEM_PORT}")
else:
    limiter = Limiter(get_remote_address, app=app)
    safe_log(logging.WARNING, "rate_limit_storage_fallback", storage="memory")


def token_count(text: str, model: str = "gpt-4") -> int:
    try:
        if model.startswith("mistral") and MistralTokenizer is not None:
            tok = MistralTokenizer.from_model("open-mistral-nemo")
            req = ChatCompletionRequest(messages=[UserMessage(content=text)], model="open-mistral-nemo")
            return len(tok.encode_chat_completion(req).tokens)
        if tiktoken is not None:
            enc = tiktoken.encoding_for_model(model if model in {"gpt-3.5-turbo", "gpt-4"} else "gpt-4")
            return len(enc.encode(text))
        return len(text.split())
    except Exception:
        return len(text.split())


def error(code: int, model: str | None = None, key: str | None = None):
    mapping = {
        1002: ("The model does not exist.", "invalid_request_error", "model_not_found", 400),
        1003: ("The requested model is not allowed by this relay.", "invalid_request_error", "model_not_allowed", 400),
        1020: ("Incorrect API key provided.", "authentication_error", "invalid_api_key", 401),
        1021: ("Invalid Authentication", "invalid_request_error", None, 401),
        1212: ("Incorrect Endpoint. Please use the /v1/chat/completions endpoint.", "invalid_request_error", "model_not_supported", 400),
        1044: ("This model does not support image inputs.", "invalid_request_error", "model_not_supported", 400),
        1412: ("No message provided.", "invalid_request_error", "invalid_request_error", 400),
        1423: ("No content in last message.", "invalid_request_error", "invalid_request_error", 400),
        1405: ("Method Not Allowed", "invalid_request_error", None, 405),
        1501: ("The upstream provider returned an error.", "upstream_error", "upstream_error", 502),
        1502: ("The upstream provider response could not be used safely.", "upstream_output_safety_error", "unsafe_reasoning_leak", 502),
        1503: ("This endpoint is unsupported in Hermes Safe Mode.", "invalid_request_error", "unsupported_in_hermes_safe_mode", 400),
    }
    msg, typ, err_code, http = mapping.get(code, ("Unknown error", "unknown_error", None, 400))
    if model and code == 1002:
        msg = msg.replace("does not exist.", f"does not exist: {model}.")
    payload = {"error": {"message": msg, "type": typ, "param": None, "code": err_code}}
    return jsonify(payload), http


def cors():
    resp = make_response()
    resp.headers["Access-Control-Allow-Origin"] = "*"
    resp.headers["Access-Control-Allow-Headers"] = "Content-Type,Authorization"
    resp.headers["Access-Control-Allow-Methods"] = "POST, OPTIONS"
    return resp, 204


def get_client_api_key():
    h = request.headers.get("Authorization", "")
    if not h.startswith("Bearer "):
        return None
    return h.split(" ", 1)[1].strip() or None


def get_api_key():
    return get_client_api_key()


def get_upstream_api_key():
    if ONE_MIN_AI_API_KEY:
        return ONE_MIN_AI_API_KEY
    if ALLOW_CLIENT_API_KEY_FALLBACK:
        return get_client_api_key()
    return None


def normalize_text(content):
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, dict) and "text" in item:
                txt = item["text"]
                parts.append("".join(txt) if isinstance(txt, list) else str(txt))
        return "\n".join(parts).strip()
    return str(content).strip() if content is not None else ""


def build_prompt(messages, new_input=""):
    lines = []
    for msg in messages:
        role = str(msg.get("role", "user")).strip().lower() or "user"
        content = normalize_text(msg.get("content", ""))
        lines.append(f"{role}: {content}")
    extra = normalize_text(new_input)
    if extra:
        lines.append(f"user: {extra}")
    prompt = "\n".join(lines)
    if MAX_PROMPT_CHARS and len(prompt) > MAX_PROMPT_CHARS:
        prompt = prompt[-MAX_PROMPT_CHARS:]
    return prompt


def upstream_error(resp):
    if resp.status_code == 401:
        return error(1020)
    safe_log(logging.WARNING, "upstream_error", status_code=getattr(resp, "status_code", None))
    return error(1501)


def set_headers(resp):
    resp.headers["Content-Type"] = "application/json"
    resp.headers["Access-Control-Allow-Origin"] = "*"
    resp.headers["X-Request-ID"] = str(uuid.uuid4())


def upload_image(url: str, headers: dict) -> str:
    if url.startswith("data:image/png;base64,"):
        data = base64.b64decode(url.split(",", 1)[1])
        fileobj = BytesIO(data)
    else:
        r = requests.get(url, timeout=REQUEST_TIMEOUT_SECONDS)
        r.raise_for_status()
        fileobj = BytesIO(r.content)
    files = {"asset": (f"relay-{uuid.uuid4()}", fileobj, "image/png")}
    r = requests.post(ASSET_URL, files=files, headers=headers, timeout=REQUEST_TIMEOUT_SECONDS)
    r.raise_for_status()
    return r.json()["fileContent"]["path"]


UNSAFE_REASONING_MARKERS = (
    "considering response to user",
    "the user is looking for",
    "i need to",
    "we need to answer",
    "analysis",
    "chain of thought",
    "internal reasoning",
    "scratchpad",
    "tool call",
    "debug",
    "provider details",
    "raw airecord",
)


def extract_assistant_text(resp_json) -> str:
    if isinstance(resp_json, dict):
        try:
            result = resp_json["aiRecord"]["aiRecordDetail"]["resultObject"]
            if isinstance(result, list) and result:
                return str(result[0])
            return str(result)
        except (KeyError, TypeError):
            pass
        for key in ("content", "text", "message", "result"):
            value = resp_json.get(key)
            if isinstance(value, str):
                return value
    raise ValueError("missing assistant content")


def sanitize_assistant_text(text: str) -> str:
    cleaned = str(text or "").strip()
    if not SANITIZE_ASSISTANT_OUTPUT:
        return cleaned
    if BLOCK_REASONING_LEAKS:
        lowered = cleaned.lower()
        if any(marker in lowered for marker in UNSAFE_REASONING_MARKERS):
            raise ValueError("unsafe reasoning leak")
    return cleaned


def build_chat_payload(model: str, prompt: str) -> dict:
    payload = {
        "type": "UNIFY_CHAT_WITH_AI",
        "model": model,
        "promptObject": {"prompt": prompt},
    }
    if HERMES_SAFE_MODE:
        payload["promptObject"]["settings"] = {
            "webSearchSettings": {
                "webSearch": False if DISABLE_1MIN_WEB_SEARCH else True,
                "numOfSite": 0 if DISABLE_1MIN_WEB_SEARCH else 1,
                "maxWord": 0 if DISABLE_1MIN_WEB_SEARCH else 500,
            },
            "historySettings": {
                "isMixed": False if DISABLE_1MIN_HISTORY else True,
                "historyMessageLimit": 0 if DISABLE_1MIN_HISTORY else 10,
            },
            "withMemories": False if DISABLE_1MIN_MEMORIES else True,
        }
    return payload


def transform_chat(resp_json, model: str, prompt_tokens: int):
    try:
        text = sanitize_assistant_text(extract_assistant_text(resp_json))
    except ValueError:
        return None
    comp_tokens = token_count(text, model)
    return {
        "id": f"chatcmpl-{uuid.uuid4()}",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": model,
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": text},
                "finish_reason": "stop",
            }
        ],
        "usage": {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": comp_tokens,
            "total_tokens": prompt_tokens + comp_tokens,
        },
    }


def synthetic_sse(text: str, model: str, prompt_tokens: int):
    stream_id = f"chatcmpl-{uuid.uuid4()}"
    created = int(time.time())
    yield "data: " + json.dumps(
        {
            "id": stream_id,
            "object": "chat.completion.chunk",
            "created": created,
            "model": model,
            "choices": [{"index": 0, "delta": {"role": "assistant"}, "finish_reason": None}],
        },
        ensure_ascii=False,
    ) + "\n\n"
    if text:
        yield "data: " + json.dumps(
            {
                "id": stream_id,
                "object": "chat.completion.chunk",
                "created": created,
                "model": model,
                "choices": [{"index": 0, "delta": {"content": text}, "finish_reason": None}],
            },
            ensure_ascii=False,
        ) + "\n\n"
    comp_tokens = token_count(text, model)
    yield "data: " + json.dumps(
        {
            "id": stream_id,
            "object": "chat.completion.chunk",
            "created": created,
            "model": model,
            "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
            "usage": {
                "prompt_tokens": prompt_tokens,
                "completion_tokens": comp_tokens,
                "total_tokens": prompt_tokens + comp_tokens,
            },
        },
        ensure_ascii=False,
    ) + "\n\n"
    yield "data: [DONE]\n\n"


def stream_chat(resp, model: str, prompt_tokens: int):
    stream_id = f"chatcmpl-{uuid.uuid4()}"
    chunks = []

    for raw in resp.iter_lines(decode_unicode=False):
        if raw == b"":
            continue
        try:
            line = raw.decode("utf-8")
        except UnicodeDecodeError:
            line = raw.decode("utf-8", errors="replace")

        if not line.startswith("data:"):
            continue

        data = line.split(":", 1)[1].strip()
        if data == "[DONE]":
            break

        try:
            parsed = json.loads(data)
            content = parsed.get("content") or parsed.get("delta", {}).get("content") or ""
        except Exception:
            content = data

        if not content:
            continue

        chunks.append(content)
        yield "data: " + json.dumps(
            {
                "id": stream_id,
                "object": "chat.completion.chunk",
                "created": int(time.time()),
                "model": model,
                "choices": [{"index": 0, "delta": {"content": content}, "finish_reason": None}],
            },
            ensure_ascii=False,
        ) + "\n\n"

    full_text = "".join(chunks)
    comp_tokens = token_count(full_text, model)
    yield "data: " + json.dumps(
        {
            "id": stream_id,
            "object": "chat.completion.chunk",
            "created": int(time.time()),
            "model": model,
            "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
            "usage": {
                "prompt_tokens": prompt_tokens,
                "completion_tokens": comp_tokens,
                "total_tokens": prompt_tokens + comp_tokens,
            },
        },
        ensure_ascii=False,
    ) + "\n\n"
    yield "data: [DONE]\n\n"


@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "GET":
        ip = socket.gethostbyname(socket.gethostname())
        return f"Congratulations! Your API is working!\n\nEndpoint: {ip}:{PORT}/v1"
    return error(1405)


@app.route("/v1/models", methods=["GET"])
@limiter.limit("500 per minute")
def models():
    model_ids = MODEL_SUBSET if STATIC_MODELS_ONLY else MODELS
    data = [{"id": m, "object": "model", "owned_by": "1minai", "created": 1727389042} for m in model_ids]
    return jsonify({"data": data, "object": "list"})


@app.route("/v1/chat/completions", methods=["POST", "OPTIONS"])
@limiter.limit("500 per minute")
def chat():
    if request.method == "OPTIONS":
        return cors()

    api_key = get_upstream_api_key()
    if not api_key:
        return error(1021)

    data = request.get_json(silent=True) or {}
    messages = data.get("messages") or []
    if not messages:
        return error(1412)

    last = messages[-1].get("content")
    if not last:
        return error(1423)

    model = data.get("model") or DEFAULT_MODEL
    if STRICT_MODELS and model not in MODEL_SUBSET:
        return error(1003, model)

    headers = {"API-KEY": api_key, "Content-Type": "application/json"}
    prompt = build_prompt(messages, data.get("new_input", ""))

    attachments = None
    content = messages[-1].get("content")
    if isinstance(content, list) and not HERMES_SAFE_MODE:
        if model not in VISION_MODELS:
            return error(1044, model)
        image_paths = []
        text_parts = []
        for item in content:
            if not isinstance(item, dict):
                continue
            if "text" in item:
                txt = item["text"]
                text_parts.append("".join(txt) if isinstance(txt, list) else str(txt))
            if "image_url" in item:
                try:
                    image_paths.append(upload_image(item["image_url"]["url"], headers))
                except Exception:
                    safe_log(logging.WARNING, "image_upload_failed")
        if image_paths:
            attachments = {"images": image_paths}
        if text_parts:
            prompt = build_prompt(messages[:-1] + [{"role": "user", "content": "\n".join(text_parts)}], data.get("new_input", ""))

    if LOG_PROMPTS and not HERMES_SAFE_MODE:
        safe_log(logging.INFO, "prompt_length", chars=len(prompt))

    prompt_tokens = token_count(prompt, model)
    payload = build_chat_payload(model, prompt)
    if attachments:
        payload["promptObject"]["attachments"] = attachments

    client_requested_stream = bool(data.get("stream", False))
    upstream_stream = client_requested_stream and not FORCE_NON_STREAMING and not SANITIZE_ASSISTANT_OUTPUT and not BLOCK_REASONING_LEAKS

    if not upstream_stream:
        r = requests.post(CHAT_URL, json=payload, headers=headers, timeout=REQUEST_TIMEOUT_SECONDS)
        if r.status_code != 200:
            return upstream_error(r)
        out = transform_chat(r.json(), model, prompt_tokens)
        if out is None:
            return error(1502)
        if client_requested_stream and SYNTHETIC_SSE_WHEN_STREAM_REQUESTED:
            text = out["choices"][0]["message"]["content"]
            return Response(synthetic_sse(text, model, prompt_tokens), content_type="text/event-stream")
        resp = make_response(jsonify(out), 200)
        set_headers(resp)
        return resp

    r = requests.post(STREAM_URL, data=json.dumps(payload), headers=headers, stream=True, timeout=REQUEST_TIMEOUT_SECONDS)
    if r.status_code != 200:
        return upstream_error(r)
    return Response(stream_chat(r, model, prompt_tokens), content_type="text/event-stream")


@app.route("/v1/images/generations", methods=["POST", "OPTIONS"])
@limiter.limit("100 per minute")
def images():
    if request.method == "OPTIONS":
        return cors()
    if HERMES_SAFE_MODE:
        return error(1503)

    api_key = get_upstream_api_key()
    if not api_key:
        return error(1021)

    data = request.get_json(silent=True) or {}
    prompt = data.get("prompt")
    if not prompt:
        return error(1412)

    model = data.get("model", "black-forest-labs/flux-schnell")
    if model not in IMAGE_MODELS:
        return error(1044, model)

    payload = {
        "type": "IMAGE_GENERATOR",
        "model": model,
        "promptObject": {
            "prompt": prompt,
            "n": data.get("n", 1),
            "size": data.get("size", "1024x1024"),
        },
    }
    headers = {"API-KEY": api_key, "Content-Type": "application/json"}

    try:
        r = requests.post(f"{FEATURES_URL}?isStreaming=false", json=payload, headers=headers, timeout=REQUEST_TIMEOUT_SECONDS)
        r.raise_for_status()
        urls = r.json()["aiRecord"]["aiRecordDetail"]["resultObject"]
        return jsonify({"created": int(time.time()), "data": [{"url": u} for u in urls]})
    except Exception:
        safe_log(logging.WARNING, "image_generation_failed")
        return error(1044, model)


def run_server():
    ip = socket.gethostbyname(socket.gethostname())
    public_ip = None
    if not HERMES_SAFE_MODE:
        try:
            public_ip = requests.get("https://api.ipify.org", timeout=10).text
        except Exception:
            public_ip = "unavailable"

    if not HERMES_SAFE_MODE:
        logger.info(
            f"""{printedcolors.Color.fg.lightcyan}
====================================================
Enjoying this self-hosted relay?
You can get a hosted, managed version at:
  https://shop.kokodev.cc
with extra features like video generation,
failover nodes, and more.
====================================================
{printedcolors.Color.reset}"""
        )

    if public_ip:
        logger.info("Server ready: internal=%s:%s public=%s endpoint=%s:%s/v1", ip, PORT, public_ip, ip, PORT)
    else:
        logger.info("Server ready: internal=%s:%s endpoint=%s:%s/v1", ip, PORT, ip, PORT)

    serve(app, host=HOST, port=PORT)


if __name__ == "__main__":
    run_server()
