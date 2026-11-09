"""Live tests against the running server (start it with serve/launch.sh first).

Covers response shapes, determinism at temperature 0 and under a fixed seed,
max_tokens, error envelopes, refusal of steward-lora when no adapter is present,
and a hot-load of a small random LoRA (written to a temp dir in the multimodal
key layout, to exercise the remap) that changes steward-lora's output without
touching steward-base. The hot-load test points the server back at its original
adapter dir when it finishes.

Run: serve/.venv/bin/python -m pytest serve/tests/test_live.py -q
Override the target with COMMISSAR_URL.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest
import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import settings  # noqa: E402

URL = os.environ.get("COMMISSAR_URL", f"http://{settings.HOST}:{settings.PORT}").rstrip("/")
PROMPT = [{"role": "system", "content": "You are a terse team steward."},
          {"role": "user", "content": "A teammate proposes skipping the tests to ship faster. One sentence reply."}]


def chat(**kw):
    body = {"model": settings.BASE_MODEL_NAME, "messages": PROMPT, "max_tokens": 40, **kw}
    return requests.post(f"{URL}/v1/chat/completions", json=body, timeout=300)


def text(resp):
    assert resp.status_code == 200, resp.text
    return resp.json()["choices"][0]["message"]["content"]


@pytest.fixture(scope="module", autouse=True)
def server_up():
    try:
        requests.get(f"{URL}/health", timeout=5).raise_for_status()
    except Exception as exc:
        pytest.skip(f"server not reachable at {URL}: {exc}")


def test_models_shape():
    body = requests.get(f"{URL}/v1/models", timeout=10).json()
    assert body["object"] == "list"
    assert settings.BASE_MODEL_NAME in [m["id"] for m in body["data"]]
    assert all(m["object"] == "model" for m in body["data"])


def test_chat_shape():
    body = chat(temperature=0).json()
    assert body["object"] == "chat.completion" and body["model"] == settings.BASE_MODEL_NAME
    choice = body["choices"][0]
    assert choice["message"]["role"] == "assistant" and isinstance(choice["message"]["content"], str)
    assert choice["message"]["content"].strip() and "<think>" not in choice["message"]["content"]
    assert choice["finish_reason"] in {"stop", "length"}
    u = body["usage"]
    assert u["prompt_tokens"] > 0 and 0 < u["completion_tokens"] <= 40
    assert u["total_tokens"] == u["prompt_tokens"] + u["completion_tokens"]


def test_temperature_zero_is_deterministic():
    outs = {text(chat(temperature=0)) for _ in range(3)}
    assert len(outs) == 1, outs


def test_seed_makes_sampling_repeatable():
    a, b = (text(chat(temperature=0.9, top_p=0.95, seed=1234)) for _ in range(2))
    assert a == b


def test_max_tokens_is_respected():
    body = chat(temperature=0, max_tokens=3).json()
    assert body["usage"]["completion_tokens"] <= 3 and body["choices"][0]["finish_reason"] == "length"


def test_stream_is_sse():
    r = requests.post(f"{URL}/v1/chat/completions", timeout=300, stream=True, json={
        "model": settings.BASE_MODEL_NAME, "messages": PROMPT, "max_tokens": 8, "temperature": 0, "stream": True})
    lines = [ln for ln in r.iter_lines(decode_unicode=True) if ln]
    assert lines[-1] == "data: [DONE]"
    assert json.loads(lines[0][6:])["object"] == "chat.completion.chunk"


@pytest.mark.parametrize("body,status", [
    ({"model": "nope", "messages": PROMPT}, 404),
    ({"model": settings.BASE_MODEL_NAME, "messages": PROMPT, "n": 2}, 400),
    ({"model": settings.BASE_MODEL_NAME}, 400),
])
def test_error_envelopes(body, status):
    r = requests.post(f"{URL}/v1/chat/completions", json=body, timeout=30)
    assert r.status_code == status and "message" in r.json()["error"]


def test_lora_refused_when_adapter_absent():
    status = requests.get(f"{URL}/admin/adapter", timeout=10).json()
    if status["found_dir"]:
        pytest.skip("an adapter is present; refusal applies only when it is absent")
    r = chat(model=settings.LORA_MODEL_NAME, temperature=0)
    assert r.status_code == 404 and r.json()["error"]["code"] == "model_not_found"
    assert settings.LORA_MODEL_NAME not in [m["id"] for m in requests.get(f"{URL}/v1/models", timeout=10).json()["data"]]


def write_fake_adapter(folder: Path, scale: float, targets=("down_proj",)) -> None:
    """A rank-8 LoRA on every down_proj, saved with multimodal key names, with random A and B.

    targets is written to adapter_config.json as given: a list of names, or a regex string.
    """
    import torch
    from huggingface_hub import hf_hub_download
    from safetensors import safe_open
    from safetensors.torch import save_file

    index = json.loads(Path(hf_hub_download(settings.BASE_MODEL_ID, "model.safetensors.index.json",
                                            revision=settings.BASE_REVISION)).read_text())["weight_map"]
    gen = torch.Generator().manual_seed(0)
    tensors = {}
    for key, shard in index.items():
        if key.startswith("model.language_model.layers.") and key.endswith("mlp.down_proj.weight"):
            path = hf_hub_download(settings.BASE_MODEL_ID, shard, revision=settings.BASE_REVISION)
            with safe_open(path, "pt") as f:
                out_f, in_f = f.get_slice(key).get_shape()
            stem = "base_model.model." + key[: -len(".weight")]
            tensors[stem + ".lora_A.weight"] = torch.randn(8, in_f, generator=gen) * scale
            tensors[stem + ".lora_B.weight"] = torch.randn(out_f, 8, generator=gen) * scale
    folder.mkdir(parents=True, exist_ok=True)
    save_file(tensors, str(folder / "adapter_model.safetensors"))
    (folder / "adapter_config.json").write_text(json.dumps({
        "peft_type": "LORA", "task_type": "CAUSAL_LM", "r": 8, "lora_alpha": 16, "lora_dropout": 0.0,
        "target_modules": targets if isinstance(targets, str) else list(targets), "bias": "none", "base_model_name_or_path": settings.BASE_MODEL_ID}))


def test_lora_hot_load_changes_output_and_spares_base(tmp_path):
    original = requests.get(f"{URL}/admin/adapter", timeout=10).json()["configured_dir"]
    if requests.get(f"{URL}/admin/adapter", timeout=10).json()["found_dir"]:
        pytest.skip("a real adapter is present; not swapping it out")
    base_before = text(chat(temperature=0))
    write_fake_adapter(tmp_path / "ckpt" / "inner", scale=0.05)
    try:
        r = requests.post(f"{URL}/admin/adapter", json={"dir": str(tmp_path / "ckpt")}, timeout=300).json()
        assert r["ready"], r
        assert r["dropped_keys"] == 0 and r["loaded_keys"] == 64
        assert settings.LORA_MODEL_NAME in [m["id"] for m in requests.get(f"{URL}/v1/models", timeout=10).json()["data"]]
        lora_out = text(chat(model=settings.LORA_MODEL_NAME, temperature=0))
        assert lora_out != base_before
        assert text(chat(temperature=0)) == base_before  # base unaffected while the LoRA is resident
        assert text(chat(model=settings.LORA_MODEL_NAME, temperature=0)) == lora_out
        # Replace the files in place: the server must notice and reload without a restart.
        # The replacement names its targets with a regex over the multimodal paths.
        write_fake_adapter(tmp_path / "ckpt" / "inner", scale=0.08, targets=r".*language_model\.layers\.\d+\.mlp\.down_proj")
        lora_out2 = text(chat(model=settings.LORA_MODEL_NAME, temperature=0))
        assert lora_out2 != lora_out
        status = requests.get(f"{URL}/admin/adapter", timeout=10).json()
        assert status["loaded"] and status["loaded_keys"] == 64 and status["last_error"] is None, status
    finally:
        back = requests.post(f"{URL}/admin/adapter", json={"dir": original}, timeout=300).json()
    assert back["loaded"] is False and back["configured_dir"] == original
    assert text(chat(temperature=0)) == base_before
    assert chat(model=settings.LORA_MODEL_NAME, temperature=0).status_code == 404


def test_mismatched_adapter_is_refused_not_half_loaded(tmp_path):
    original = requests.get(f"{URL}/admin/adapter", timeout=10).json()
    if original["found_dir"]:
        pytest.skip("a real adapter is present; not swapping it out")
    folder = tmp_path / "broken"
    write_fake_adapter(folder, scale=0.05)
    from safetensors.torch import load_file, save_file
    state = load_file(str(folder / "adapter_model.safetensors"))
    save_file({k: v for k, v in state.items() if ".layers.0." not in k}, str(folder / "adapter_model.safetensors"))
    try:
        r = requests.post(f"{URL}/admin/adapter", json={"dir": str(folder)}, timeout=300).json()
        assert r["ready"] is False and r["loaded"] is False and "missing" in (r["last_error"] or ""), r
        assert chat(model=settings.LORA_MODEL_NAME, temperature=0).status_code == 404
    finally:
        requests.post(f"{URL}/admin/adapter", json={"dir": original["configured_dir"]}, timeout=300)


def test_stop_string_cuts_inside_the_completion():
    msgs = [{"role": "user", "content": "List three fruits, one per line, no other text."}]
    body = chat(messages=msgs, temperature=0, max_tokens=40, stop=["\n"]).json()
    content = body["choices"][0]["message"]["content"]
    assert body["choices"][0]["finish_reason"] == "stop" and content.strip() and "\n" not in content
    assert body["usage"]["completion_tokens"] > 1


def test_top_p_zero_is_honoured_as_near_greedy():
    assert text(chat(temperature=0.9, top_p=0, seed=1)) == text(chat(temperature=0.9, top_p=0, seed=2))


@pytest.mark.parametrize("path,payload", [
    ("/v1/chat/completions", {"model": settings.BASE_MODEL_NAME, "messages": PROMPT,
                              "chat_template_kwargs": {"tokenize": False}}),
    ("/admin/adapter", {"dir": 5}),
])
def test_bad_inputs_are_400_not_500(path, payload):
    assert requests.post(f"{URL}{path}", json=payload, timeout=30).status_code == 400


def test_malformed_body_is_400():
    r = requests.post(f"{URL}/v1/chat/completions", data=b"\xff\xfe{not json", timeout=30,
                      headers={"Content-Type": "application/json"})
    assert r.status_code == 400
