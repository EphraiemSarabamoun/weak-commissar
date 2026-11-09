"""OpenAI-compatible HTTP server for the commissar (entry point).

Routes (bound to 127.0.0.1 only):
  GET  /health                 liveness, models, adapter status, VRAM use
  GET  /v1/models              steward-base, plus steward-lora when the adapter files exist
  POST /v1/chat/completions    OpenAI chat completions (stream=true is re-emitted as SSE)
  GET  /admin/adapter          adapter slot status
  POST /admin/adapter          {"dir": "<path>" | null}: repoint the slot and hot-(re)load

Run it through launch.sh, which starts it in the tmux session commissar-serve.
Directly: serve/.venv/bin/python serve/server.py [--port N] [--adapter-dir PATH]
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
# Number GPUs as nvidia-smi does, so the VRAM guard and torch look at the same device.
os.environ.setdefault("CUDA_DEVICE_ORDER", "PCI_BUS_ID")

import adapters  # noqa: E402
import openai_schema as schema  # noqa: E402
import settings  # noqa: E402
from engine import Engine  # noqa: E402

ENGINE = Engine()
SLOT = adapters.AdapterSlot(settings.ADAPTER_DIR)
STARTED = int(time.time())


def log(event: str, **fields) -> None:
    print(json.dumps({"t": time.strftime("%Y-%m-%dT%H:%M:%S"), "event": event, **fields}), flush=True)


def model_names() -> list[str]:
    names = [settings.BASE_MODEL_NAME]
    if SLOT.available():
        names.append(settings.LORA_MODEL_NAME)
    return names


def chat(body) -> tuple[dict, bool]:
    """Validate, route to base or LoRA, generate; return (completion object, stream flag)."""
    req = schema.parse_chat_request(body)
    if req.model not in (settings.BASE_MODEL_NAME, settings.LORA_MODEL_NAME):
        raise schema.ApiError(404, f"model {req.model!r} does not exist; available: {model_names()}",
                              code="model_not_found", param="model")
    with ENGINE.lock:
        adapter_name = None
        if req.model == settings.LORA_MODEL_NAME:
            if not SLOT.sync(ENGINE):
                why = SLOT.last_error or f"no adapter_config.json + adapter_model.safetensors under {SLOT.root}"
                raise schema.ApiError(404, f"{settings.LORA_MODEL_NAME} is not available: {why}",
                                      code="model_not_found", param="model")
            adapter_name = SLOT.loaded.name
        gen = ENGINE.generate(req, adapter_name)
    content, reasoning = schema.split_thinking(gen.text, req.enable_thinking)
    timing = {"seconds": round(gen.seconds, 3),
              "tokens_per_second": round(gen.completion_tokens / gen.seconds, 2) if gen.seconds else None}
    log("chat", model=req.model, prompt_tokens=gen.prompt_tokens, completion_tokens=gen.completion_tokens,
        finish=gen.finish_reason, temperature=req.temperature, seed=req.seed, **timing)
    return schema.completion_body(req.model, content, reasoning, gen.finish_reason,
                                  gen.prompt_tokens, gen.completion_tokens, timing), req.stream


class Handler(BaseHTTPRequestHandler):
    server_version = "commissar-serve/1"

    def log_message(self, fmt, *args):  # route access logs through log() instead of stderr
        pass

    def _send(self, status: int, body: dict) -> None:
        data = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _send_stream(self, body: dict) -> None:
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        for chunk in schema.stream_chunks(body):
            self.wfile.write(f"data: {json.dumps(chunk)}\n\n".encode())
        self.wfile.write(b"data: [DONE]\n\n")

    def _json_body(self):
        try:
            length = int(self.headers.get("Content-Length") or 0)
            return json.loads(self.rfile.read(length) or b"null")
        except ValueError as exc:  # bad Content-Length, invalid JSON, or undecodable bytes
            raise schema.ApiError(400, f"body is not valid JSON: {exc}") from exc

    def _guard(self, fn):
        """Run a route, mapping ApiError, CUDA OOM and anything else to OpenAI error bodies."""
        try:
            fn()
        except schema.ApiError as err:
            log("error", path=self.path, status=err.status, message=err.message)
            self._send(err.status, err.body())
        except Exception as exc:
            oom = type(exc).__name__ == "OutOfMemoryError"
            if oom:
                ENGINE.torch.cuda.empty_cache()
            log("error", path=self.path, status=503 if oom else 500, message=repr(exc),
                trace=traceback.format_exc(limit=4))
            err = schema.ApiError(503 if oom else 500, f"{type(exc).__name__}: {exc}",
                                  err_type="server_error", code="out_of_memory" if oom else None)
            self._send(err.status, err.body())

    def do_GET(self):
        def route():
            if self.path == "/health":
                self._send(200, {"status": "ok", "base_model": f"{settings.BASE_MODEL_ID}@{settings.BASE_REVISION}",
                                 "models": model_names(), "adapter": SLOT.status(), "vram": ENGINE.vram(),
                                 "port": settings.PORT, "started": STARTED})
            elif self.path == "/v1/models":
                self._send(200, schema.models_body(model_names(), STARTED))
            elif self.path == "/admin/adapter":
                self._send(200, SLOT.status())
            else:
                raise schema.ApiError(404, f"no route GET {self.path}", code="not_found")
        self._guard(route)

    def do_POST(self):
        def route():
            if self.path == "/v1/chat/completions":
                body, stream = chat(self._json_body())
                self._send_stream(body) if stream else self._send(200, body)
            elif self.path == "/admin/adapter":
                body = self._json_body() or {}
                new_dir = body.get("dir") if isinstance(body, dict) else None
                if new_dir is not None and not isinstance(new_dir, str):
                    raise schema.ApiError(400, "dir must be a path string or null", param="dir")
                with ENGINE.lock:
                    SLOT.set_root(Path(new_dir).expanduser() if new_dir else None)
                    ready = SLOT.sync(ENGINE)
                log("adapter", dir=new_dir, ready=ready, error=SLOT.last_error)
                self._send(200, {"ready": ready, **SLOT.status()})
            else:
                raise schema.ApiError(404, f"no route POST {self.path}", code="not_found")
        self._guard(route)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--port", type=int, default=settings.PORT)
    parser.add_argument("--adapter-dir", type=Path, default=settings.ADAPTER_DIR)
    args = parser.parse_args()
    settings.PORT = args.port
    SLOT.set_root(args.adapter_dir.expanduser())
    try:
        ENGINE.load()
    except Exception as exc:
        log("refused_start", reason=str(exc))
        return 3
    with ENGINE.lock:
        SLOT.sync(ENGINE)  # load the adapter now if it is already present
    httpd = ThreadingHTTPServer((settings.HOST, args.port), Handler)
    httpd.daemon_threads = True
    log("listening", url=f"http://{settings.HOST}:{args.port}/v1", models=model_names(),
        adapter=SLOT.status(), vram=ENGINE.vram())
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        log("shutdown")
    return 0


if __name__ == "__main__":
    sys.exit(main())
