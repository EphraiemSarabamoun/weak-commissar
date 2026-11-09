"""The resident model: load it once under the VRAM guard, generate, attach and drop LoRAs.

Data flow: server.py hands a validated ChatRequest to Engine.generate, which
renders it with Qwen3.5's own chat template, runs transformers generate on the
5090 in bf16, and returns the decoded text with token counts and timing.

One generation runs at a time (Engine.lock), at batch size 1, so a temperature-0
request is plain greedy decoding over the same kernels every time and repeats
exactly. Callers hold the lock across adapter changes and generation, because
attaching a LoRA mutates the model in place.
"""

from __future__ import annotations

import dataclasses
import threading
import time
from pathlib import Path

import adapters
import gpu_guard
import settings
from openai_schema import ApiError, ChatRequest


@dataclasses.dataclass
class Generation:
    text: str
    finish_reason: str
    prompt_tokens: int
    completion_tokens: int
    seconds: float


class Engine:
    """Owns the tokenizer, the base model and (after the first LoRA) its PeftModel wrapper."""

    def __init__(self):
        self.lock = threading.Lock()
        self.model = None   # Qwen3_5ForCausalLM, bf16, on cuda:0
        self.peft = None    # PeftModel wrapping self.model once an adapter is attached
        self.tok = None
        self.free_gb_at_start = None

    # ----- loading -------------------------------------------------------------------

    def load(self) -> None:
        """Check free VRAM, cap our allocator, then load tokenizer and text-only model."""
        self.free_gb_at_start = gpu_guard.require_free_vram()
        import torch
        from transformers import AutoModelForCausalLM, AutoTokenizer

        self.torch = torch
        gpu_guard.cap_allocator(torch)
        self.tok = AutoTokenizer.from_pretrained(settings.BASE_MODEL_ID, revision=settings.BASE_REVISION)
        # AutoModelForCausalLM on this checkpoint yields Qwen3_5ForCausalLM: the decoder
        # only, without the vision tower, which saves VRAM the commissar never uses.
        self.model = AutoModelForCausalLM.from_pretrained(
            settings.BASE_MODEL_ID, revision=settings.BASE_REVISION,
            dtype=torch.bfloat16, device_map=f"cuda:{settings.GPU_INDEX}",
        ).eval()
        # Stop on <|im_end|> (end of the assistant turn) as well as <|endoftext|>.
        self.eos_ids = sorted({self.tok.convert_tokens_to_ids("<|im_end|>"), self.tok.convert_tokens_to_ids("<|endoftext|>")})
        self.pad_id = self.tok.convert_tokens_to_ids("<|endoftext|>")

    def vram(self) -> dict:
        t = self.torch
        return {
            "allocated_gb": round(t.cuda.memory_allocated() / 2**30, 3),
            "reserved_gb": round(t.cuda.memory_reserved() / 2**30, 3),
            "peak_allocated_gb": round(t.cuda.max_memory_allocated() / 2**30, 3),
            "cap_gb": settings.ALLOCATOR_CAP_GB,
            "device_free_gb_at_start": round(self.free_gb_at_start, 3),
        }

    # ----- generation ----------------------------------------------------------------

    def _render(self, req: ChatRequest):
        try:
            enc = self.tok.apply_chat_template(
                req.messages, add_generation_prompt=True, enable_thinking=req.enable_thinking,
                return_dict=True, return_tensors="pt",
            )
        except Exception as exc:  # the template raises on malformed conversations
            raise ApiError(400, f"chat template rejected the messages: {exc}", param="messages") from exc
        if enc["input_ids"].shape[1] > settings.MAX_INPUT_TOKENS:
            raise ApiError(400, f"prompt is {enc['input_ids'].shape[1]} tokens; the limit is {settings.MAX_INPUT_TOKENS}",
                           param="messages", code="context_length_exceeded")
        return {k: v.to(self.model.device) for k, v in enc.items()}

    def _generation_config(self, req: ChatRequest):
        from transformers import GenerationConfig

        common = dict(max_new_tokens=req.max_tokens, eos_token_id=self.eos_ids, pad_token_id=self.pad_id)
        if req.greedy:
            return GenerationConfig(do_sample=False, **common)
        # top_k=0 disables top-k so only the OpenAI knobs (temperature, top_p) shape sampling.
        return GenerationConfig(do_sample=True, temperature=req.temperature, top_p=req.top_p, top_k=0, **common)

    def _stop_criteria(self, stops: list[str], n_prompt: int):
        """Stop when a stop string appears in the completion. transformers' own stop_strings
        also match across the prompt's last tokens, which can end a reply on its first token."""
        from transformers import StoppingCriteria, StoppingCriteriaList

        tok, torch = self.tok, self.torch

        class CompletionStop(StoppingCriteria):
            def __call__(self, input_ids, scores, **kwargs):
                tail = input_ids[0, n_prompt:][-64:]  # the stop must lie inside the completion
                text = tok.decode(tail, skip_special_tokens=True)
                hit = any(s in text for s in stops)
                return torch.full((input_ids.shape[0],), hit, dtype=torch.bool, device=input_ids.device)

        return StoppingCriteriaList([CompletionStop()])

    def generate(self, req: ChatRequest, adapter_name: str | None) -> Generation:
        """Generate one reply. adapter_name None means the bare base model. Hold self.lock."""
        torch = self.torch
        inputs = self._render(req)
        n_prompt = inputs["input_ids"].shape[1]
        if not req.greedy:
            if req.seed is not None:
                torch.manual_seed(req.seed)
            else:
                torch.seed()
        gen_kwargs = dict(generation_config=self._generation_config(req))
        if req.stop:
            gen_kwargs["stopping_criteria"] = self._stop_criteria(req.stop, n_prompt)
        torch.cuda.synchronize()
        t0 = time.perf_counter()
        with torch.inference_mode():
            if self.peft is None:
                out = self.model.generate(**inputs, **gen_kwargs)
            elif adapter_name is None:
                with self.peft.disable_adapter():
                    out = self.peft.generate(**inputs, **gen_kwargs)
            else:
                self.peft.set_adapter(adapter_name)
                out = self.peft.generate(**inputs, **gen_kwargs)
        torch.cuda.synchronize()
        seconds = time.perf_counter() - t0
        return self._decode(out[0, n_prompt:].tolist(), req, n_prompt, seconds)

    def _decode(self, ids: list[int], req: ChatRequest, n_prompt: int, seconds: float) -> Generation:
        n_gen = len(ids)
        finish = "length"
        if ids and ids[-1] in self.eos_ids:
            ids, finish = ids[:-1], "stop"
        text = self.tok.decode(ids, skip_special_tokens=True)
        cuts = [text.find(s) for s in req.stop if s in text]
        if cuts:
            text, finish = text[:min(cuts)], "stop"
        return Generation(text, finish, n_prompt, n_gen, seconds)

    # ----- adapters ------------------------------------------------------------------

    def attach_adapter(self, name: str, folder: Path) -> tuple[int, int]:
        """Inject and fill a LoRA named `name` from folder. Returns (loaded_keys, dropped_keys).

        Refuses (and removes the half-built adapter) unless every expected LoRA weight
        is filled by exactly the file's weights. Hold self.lock.
        """
        from peft import LoraConfig, get_peft_model, get_peft_model_state_dict, set_peft_model_state_dict
        from safetensors.torch import load_file

        cfg = adapters.read_config(folder)
        cfg.setdefault("task_type", "CAUSAL_LM")
        names = [n for n, _ in self.model.named_modules()]
        cfg["target_modules"] = adapters.resolve_targets(cfg.get("target_modules"), names)
        for key in ("rank_pattern", "alpha_pattern"):
            cfg[key] = adapters.remap_patterns(cfg.get(key) or {}, names)
        fields = {f.name for f in dataclasses.fields(LoraConfig) if f.init}
        lora_cfg = LoraConfig(**{k: v for k, v in cfg.items() if k in fields})
        state, dropped = adapters.remap_state_dict(load_file(str(folder / adapters.WEIGHTS_FILE), device="cpu"))

        first = self.peft is None
        if first:
            self.peft = get_peft_model(self.model, lora_cfg, adapter_name=name)
        else:
            self.peft.add_adapter(name, lora_cfg)
        try:
            expected = set(get_peft_model_state_dict(self.peft, adapter_name=name))
            missing, unexpected = expected - set(state), set(state) - expected
            if missing or unexpected:
                raise adapters.AdapterError(
                    f"adapter weights do not match the model: {len(missing)} missing (e.g. {sorted(missing)[:2]}), "
                    f"{len(unexpected)} unexpected (e.g. {sorted(unexpected)[:2]})")
            set_peft_model_state_dict(self.peft, state, adapter_name=name)
            self.peft.set_adapter(name)
            self.peft.eval()
        except Exception:
            self.drop_adapter(name)
            raise
        return len(state), len(dropped)

    def drop_adapter(self, name: str) -> None:
        """Remove one adapter; removing the last one restores the bare base model."""
        if self.peft is None:
            return
        remaining = [a for a in self.peft.peft_config if a != name]
        if not remaining:
            self.model = self.peft.unload()
            self.peft = None
        else:
            if name in self.peft.peft_config:
                self.peft.set_adapter(remaining[-1])
                self.peft.delete_adapter(name)
        self.torch.cuda.empty_cache()
