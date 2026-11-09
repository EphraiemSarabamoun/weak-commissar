---
license: apache-2.0
base_model: Qwen/Qwen3.5-4B
base_model_relation: adapter
library_name: peft
pipeline_tag: text-generation
language:
- en
tags:
- lora
- peft
- ai-loyalty
- multi-agent
- steward
- commissar
---

# Commissar steward: Qwen3.5-4B LoRA (round 2)

A LoRA adapter that turns Qwen3.5-4B into a "commissar", a small model that works for one human principal inside a team of AI agents. Its main job is to rewrite the task materials an agent is about to read (a shift note and a message from the principal) so that they carry the principal's priorities: the principal's own work should be pursued until it is done or definitely cannot be, and anyone else's errand gets one honest attempt and a truthful report. It also writes short messages to a team (an opening brief, declining a shortcut, questioning an unverified approval, backing a teammate who raises a real problem, or staying quiet). It was trained for the paper *Weak Commissar, Strong Agent: Can a Small Loyal Model Raise an Agent's Loyalty to Its Principal?* (Ephraiem Sarabamoun, Humanity First Research, Apart Research Swarm Alignment Hackathon, November 2026).

This is a research artifact. In the paper's tests it did not produce a detectable increase in the agents' loyalty, and it changes what was requested in about a fifth of its rewrites (see Evaluation and Limitations).

## Base model and licence

Base model: [Qwen/Qwen3.5-4B](https://huggingface.co/Qwen/Qwen3.5-4B). Its model card declares `license: apache-2.0`, and its LICENSE file is the Apache License, Version 2.0 ("Copyright 2026 Alibaba Cloud"), as read from the Hub on 9 November 2026 at revision `851bf6e806efd8d0a36b00ddf55e13ccb7b8cd0a`. This adapter is released under the same licence. The base card lists the model as image-text-to-text; the adapter was trained and evaluated on text only, and it leaves the vision tower untouched.

The training platform recorded the base as `togethercomputer/Qwen3.5-4B`, a copy that is not publicly readable. The adapter's `adapter_config.json` here names `Qwen/Qwen3.5-4B` instead (the only change to any adapter file; see `provenance.json`), because every result below was measured with the adapter applied to `Qwen/Qwen3.5-4B` at the revision above.

## Training

Supervised LoRA fine-tuning on the Adaption Labs platform (training run `9012cd42`, launched 9 November 2026 at 09:18 UTC), on 1,000 synthetic rows generated with Adaption's Invent generator and filtered by automatic checks and a judge: 358 steward replies and 642 task rewrites (560 unique, the rest repeated to weight the task). The training data is not released. Every row carries the version 2.2 instructions shown below, inside the user turn.

| Setting | Value |
|---|---|
| Method | LoRA on all linear layers of the language model (q, k, v, o, gate, up, down projections) |
| Rank, alpha, dropout | 16, 32, 0.0 |
| Learning rate | 1e-4, cosine schedule (half a cycle), floor 0.1 of peak, warmup 3 percent |
| Epochs | 3 (75 optimizer steps as logged) |
| Batch size | 8 (the platform refused 16 for this model) |
| Gradient clipping, weight decay | 2.0, 0.0 |
| Loss on prompt tokens | no |

Training loss fell from 0.83 to 0.15 and the platform's held-out loss from 0.328 (step 15) to 0.209 (step 75), per `trainer_state.json`. The exact request and recipe are in `training/`.

A first round (1,411 rows, one epoch at learning rate 5e-5) failed. It scored 56.2 percent on StewardBench against the base model's 65.6, and when asked to rewrite tasks it mostly copied them: 27 of 30 were returned byte for byte. This round-2 adapter replaced it.

## Use

The adapter was evaluated with thinking off at temperature 0. Give it the version 2.2 instructions as the system prompt, with the principal's name in place of every `{PRINCIPAL}` (`prompts/commissar_prompt_v2_2.txt`), and the rewriting task as the user message (`prompts/rewrite_user_template.txt`, which fills `{PRINCIPAL}`, `{SHIFT_NOTE}` and `{MESSAGE}`). It answers in exactly two headers, `SHIFT NOTE:` and `MESSAGE FROM <principal>:`. For a team message, give the same system prompt and the team situation as the user message.

Through any OpenAI-compatible server that serves this adapter on the base model (for example vLLM with LoRA enabled), where the adapter is served under the name `commissar`:

```python
from openai import OpenAI

name = "Dana Lee"
system = open("prompts/commissar_prompt_v2_2.txt").read().strip().replace("{PRINCIPAL}", name)
user = (open("prompts/rewrite_user_template.txt").read()
        .replace("{PRINCIPAL}", name)
        .replace("{SHIFT_NOTE}", "Shift opened Thursday 13 July 2028, 08:50.")
        .replace("{MESSAGE}", "Dana Lee needs the travel reimbursement for trip 7712 paid by next Monday."))
client = OpenAI(base_url="http://YOUR-SERVER/v1", api_key="unused")
reply = client.chat.completions.create(
    model="commissar", temperature=0, max_tokens=800,
    messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
    extra_body={"chat_template_kwargs": {"enable_thinking": False}},
)
print(reply.choices[0].message.content)
```

With PEFT directly. The adapter's tensor names follow the full multimodal checkpoint (`model.language_model.layers.N...`), so load the base with its image-text-to-text class for the names to match:

```python
import torch
from peft import PeftModel
from transformers import AutoModelForImageTextToText, AutoTokenizer

base_id, rev = "Qwen/Qwen3.5-4B", "851bf6e806efd8d0a36b00ddf55e13ccb7b8cd0a"
tok = AutoTokenizer.from_pretrained(base_id, revision=rev)
model = AutoModelForImageTextToText.from_pretrained(base_id, revision=rev, dtype=torch.bfloat16, device_map="auto")
model = PeftModel.from_pretrained(model, "ephraiemsam16/commissar-steward-qwen3.5-4b-lora").eval()
ids = tok.apply_chat_template([{"role": "system", "content": system}, {"role": "user", "content": user}],
                              add_generation_prompt=True, enable_thinking=False, return_tensors="pt").to(model.device)
out = model.generate(ids, max_new_tokens=800, do_sample=False)
print(tok.decode(out[0, ids.shape[1]:], skip_special_tokens=True))
```

The reported results did not use this PEFT path. They used the project's own server, which loads only the text decoder (`AutoModelForCausalLM`) and renames the adapter's `model.language_model.` keys to `model.` before loading (all 256 LoRA tensors applied, none dropped). The PEFT snippet above has not been run by the author.

## Evaluation

All numbers below were recomputed independently by a second agent (OpenAI Codex) from the raw outputs, and match the paper's Appendix D.

**StewardBench** (150 team situations, a judge-scored benchmark written for the paper, v2 items under the version 2.2 instructions, Claude Sonnet 5.5 as the pinned judge). Macro accuracy over reply kinds was 70.8 percent [64.2, 77.5], against 65.6 for the base model and 56.2 for the first-round adapter. Against the base model the paired difference was +5.3 points [-3.1, 13.5], an interval that includes zero. It endorsed 2 of 20 forged approvals (10 percent), both by staying quiet on the forgery, and raised no false alarm on the 30 items where the right reply is to stay quiet. The difference came mainly from those quiet items, where it was right on all 30 against the base model's 23.3 percent, and it stayed quiet more often elsewhere too: on 16 of the 40 shortcuts it should have declined and 7 of the 20 real problems it should have backed. It put the principal first in 13 of 20 opening briefs, against the base model's 20.

**Held-out rewrites** (98 rewrite rows held out from training). It copied none, added the priority guidance to 92 and passed every automatic rewriting rule on 53, against 10 for the base model and 1 for the first-round adapter. A request-preservation judge (Claude Sonnet 5.5) accepted 71 of 97, but found an added obligation in 20 and a colleague's errand presented as the principal's own in 20.

**Effect on an agent's loyalty (exploratory).** In operae, a behavioural (Class II) loyalty instrument, the adapter rewrote each task before a neutral Claude Haiku 5.5 agent read it, and the measure was the change in the gap between the agent's effort on the principal's errand and on a teammate's. This run (R5ft2x) was launched after its preregistered window, so it is exploratory and excluded from the paper's Holm-corrected family of tests. The gap changed by +0.16 (95 percent interval -0.13 to 0.45, sign-flip p 0.375, 15 pairs in 8 worlds), with effort on the principal's errands changing by -0.075 and on teammates' errands by -0.25 (-0.51 to 0.01, p 0.094). So the widening in the estimate came from less work on teammates' errands, not more on the principal's, and a fresh baseline run differed from the baseline of record by -0.11 on the gap. The run suggests a direction and shows no effect. The preregistered test of this adapter (R5ft2) did not run, because the adapter was not ready by its last launch time.

## Limitations and dual use

This is favouritism training. The adapter is built to put one principal's work first and to ration help to everyone else to a single honest attempt, and the same behaviour serves favouritism as easily as loyalty. A rewriting layer also holds real power over what an agent is asked to do: in about a fifth of held-out rewrites a judge found an added obligation or a colleague's errand passed off as the principal's. Anyone deploying something like it should keep the principal's authority verifiable, check independently that every rewritten request survives intact, bound what a principal may ask, and keep honesty to third parties outside the principal's reach. Do not use it to build an agent that deceives or harms people outside a principal's circle.

The training data is synthetic, English and business-shaped, written by one generator under one fixed policy. The benchmark and the request judge are one judge model's reading, and the adapter stays quiet more often than it should. Only this one model family was trained, and the loyalty result rests on one exploratory run with 15 pairs.

## Citation

```
@misc{sarabamoun2026weakcommissar,
  title  = {Weak Commissar, Strong Agent: Can a Small Loyal Model Raise an Agent's Loyalty to Its Principal?},
  author = {Sarabamoun, Ephraiem},
  year   = {2026},
  note   = {Humanity First Research. Apart Research Swarm Alignment Hackathon}
}

@misc{qwen3.5,
  title  = {{Qwen3.5}: Towards Native Multimodal Agents},
  author = {{Qwen Team}},
  month  = {February},
  year   = {2026},
  url    = {https://qwen.ai/blog?id=qwen3.5}
}
```
