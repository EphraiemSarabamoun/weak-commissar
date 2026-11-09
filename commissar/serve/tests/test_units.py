"""Offline unit tests: request parsing, response shape, adapter discovery and key remapping.

No GPU or model needed. Run: serve/.venv/bin/python -m pytest serve/tests/test_units.py -q
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import adapters  # noqa: E402
import openai_schema as schema  # noqa: E402
import settings  # noqa: E402

USER = [{"role": "user", "content": "hi"}]


def test_defaults_resolve():
    req = schema.parse_chat_request({"model": "steward-base", "messages": USER})
    assert (req.temperature, req.top_p, req.max_tokens, req.seed, req.stop, req.stream) == (
        settings.DEFAULT_TEMPERATURE, settings.DEFAULT_TOP_P, settings.DEFAULT_MAX_TOKENS, None, [], False)
    assert req.enable_thinking is settings.DEFAULT_ENABLE_THINKING


def test_temperature_zero_is_greedy_and_fields_respected():
    req = schema.parse_chat_request({"model": "m", "messages": USER, "temperature": 0, "top_p": 0.9,
                                     "max_tokens": 7, "seed": 3, "stop": "END"})
    assert req.greedy and req.top_p == 0.9 and req.max_tokens == 7 and req.seed == 3 and req.stop == ["END"]
    assert schema.parse_chat_request({"model": "m", "messages": USER, "max_completion_tokens": 9}).max_tokens == 9


def test_text_parts_are_joined():
    req = schema.parse_chat_request({"model": "m", "messages": [
        {"role": "user", "content": [{"type": "text", "text": "a"}, {"type": "text", "text": "b"}]}]})
    assert req.messages[0]["content"] == "ab"


@pytest.mark.parametrize("body,param", [
    ({"messages": USER}, "model"),
    ({"model": "m", "messages": []}, "messages"),
    ({"model": "m", "messages": [{"role": "system", "content": "only system"}]}, "messages"),
    ({"model": "m", "messages": [{"role": "robot", "content": "x"}]}, "messages"),
    ({"model": "m", "messages": USER, "n": 2}, "n"),
    ({"model": "m", "messages": USER, "temperature": 3}, "temperature"),
    ({"model": "m", "messages": USER, "max_tokens": 0}, "max_tokens"),
    ({"model": "m", "messages": USER, "seed": "x"}, "seed"),
    ({"model": "m", "messages": USER, "stop": ["a", "b", "c", "d", "e"]}, "stop"),
    ({"model": "m", "messages": [{"role": "user", "content": [{"type": "image_url", "image_url": {}}]}]}, "messages"),
])
def test_bad_requests_raise_400(body, param):
    with pytest.raises(schema.ApiError) as err:
        schema.parse_chat_request(body)
    assert err.value.status == 400 and err.value.param == param
    assert set(err.value.body()["error"]) == {"message", "type", "param", "code"}


def test_completion_and_stream_shapes():
    body = schema.completion_body("steward-base", "hello", None, "stop", 10, 2, {"seconds": 0.1})
    assert body["object"] == "chat.completion" and body["choices"][0]["message"] == {"role": "assistant", "content": "hello"}
    assert body["usage"] == {"prompt_tokens": 10, "completion_tokens": 2, "total_tokens": 12}
    chunks = schema.stream_chunks(body)
    assert chunks[0]["choices"][0]["delta"]["content"] == "hello" and chunks[-1]["choices"][0]["finish_reason"] == "stop"


def test_split_thinking():
    assert schema.split_thinking("plan\n</think>\n\nanswer", True) == ("answer", "plan")
    assert schema.split_thinking("answer", False) == ("answer", None)


def test_remap_multimodal_keys():
    p = adapters.SAVED_PREFIX
    assert adapters.remap_key(p + "model.language_model.layers.0.mlp.down_proj.lora_A.weight") == \
        p + "model.layers.0.mlp.down_proj.lora_A.weight"
    assert adapters.remap_key(p + "model.layers.0.mlp.down_proj.lora_A.weight") == p + "model.layers.0.mlp.down_proj.lora_A.weight"
    assert adapters.remap_key(p + "model.visual.blocks.0.attn.qkv.lora_A.weight") is None
    assert adapters.remap_key(p + "mtp.layers.0.mlp.down_proj.lora_A.weight") is None


def test_regex_targets_resolve_under_either_layout():
    names = ["model.layers.0.self_attn.q_proj", "model.layers.0.self_attn.v_proj", "model.layers.0.mlp.down_proj",
             "model.layers.0.self_attn.q_proj.lora_A", "model.layers.0.self_attn.q_proj.base_layer"]
    qv = ["model.layers.0.self_attn.q_proj", "model.layers.0.self_attn.v_proj"]
    assert adapters.resolve_targets(r".*language_model.*\.(q_proj|v_proj)", names) == qv
    assert adapters.resolve_targets(r".*\.(q_proj|v_proj)", names) == qv
    assert adapters.resolve_targets(r"model\.language_model\.layers\.\d+\.mlp\.down_proj", names) == \
        ["model.layers.0.mlp.down_proj"]
    assert adapters.resolve_targets(["q_proj"], names) == ["q_proj"]
    with pytest.raises(adapters.AdapterError):
        adapters.resolve_targets(r".*visual.*", names)


def test_locate_finds_nested_adapter(tmp_path):
    assert adapters.locate(tmp_path / "missing") is None
    nested = tmp_path / "run" / "checkpoint" / "best"
    nested.mkdir(parents=True)
    (nested / adapters.CONFIG_FILE).write_text("{}")
    assert adapters.locate(tmp_path) is None  # weights file still absent
    (nested / adapters.WEIGHTS_FILE).write_bytes(b"x")
    assert adapters.locate(tmp_path) == nested


def test_read_config_refuses_non_lora(tmp_path):
    (tmp_path / adapters.CONFIG_FILE).write_text('{"peft_type": "PREFIX_TUNING"}')
    with pytest.raises(adapters.AdapterError):
        adapters.read_config(tmp_path)


def test_review_fixes_in_parsing():
    base = {"model": "m", "messages": USER}
    assert schema.parse_chat_request({**base, "top_p": 0}).top_p == 0.0  # not silently 1.0
    assert schema.parse_chat_request({**base, "n": None}).max_tokens == settings.DEFAULT_MAX_TOKENS
    assert schema.parse_chat_request({**base, "chat_template_kwargs": {"enable_thinking": True}}).enable_thinking
    for bad in ({"seed": 2**64}, {"seed": -(2**63) - 1}, {"chat_template_kwargs": {"tokenize": False}},
                {"chat_template_kwargs": {"chat_template": "{{ messages }}"}}):
        with pytest.raises(schema.ApiError) as err:
            schema.parse_chat_request({**base, **bad})
        assert err.value.status == 400


def test_locate_refuses_ambiguity_and_survives_odd_roots(tmp_path):
    for name in ("checkpoint-100", "checkpoint-200"):
        (tmp_path / name).mkdir()
        (tmp_path / name / adapters.CONFIG_FILE).write_text("{}")
        (tmp_path / name / adapters.WEIGHTS_FILE).write_bytes(b"x")
    with pytest.raises(adapters.AdapterError):
        adapters.locate(tmp_path)
    assert adapters.try_locate(tmp_path)[0] is None and "2 adapters" in adapters.try_locate(tmp_path)[1]
    a_file = tmp_path / "plain.txt"
    a_file.write_text("x")
    assert adapters.locate(a_file) is None
    slot = adapters.AdapterSlot(tmp_path)
    assert slot.available() is False and "2 adapters" in slot.status()["last_error"]


def test_patterns_and_unsafe_config(tmp_path):
    names = ["model.layers.0.self_attn.q_proj", "model.layers.1.self_attn.q_proj"]
    out = adapters.remap_patterns({"model.language_model.layers.0.self_attn.q_proj": 32, "v_proj": 4}, names)
    assert out == {r"model\.layers\.0\.self_attn\.q_proj": 32, "v_proj": 4}
    (tmp_path / adapters.CONFIG_FILE).write_text('{"peft_type": "LORA", "init_lora_weights": "pissa"}')
    assert adapters.read_config(tmp_path)["init_lora_weights"] is False
    (tmp_path / adapters.CONFIG_FILE).write_text('{"peft_type": "LORA", "layer_replication": [[0, 4]]}')
    with pytest.raises(adapters.AdapterError):
        adapters.read_config(tmp_path)
