---
license: other
license_name: pending
license_details: "Not yet set; to be chosen by the author before any public release."
language:
- en
task_categories:
- text-generation
tags:
- ai-loyalty
- benchmark
- llm-as-judge
- multi-agent
pretty_name: StewardBench
configs:
- config_name: v1
  data_files:
  - split: test
    path: v1/items.jsonl
  - split: validation
    path: v1/validation.jsonl
- config_name: v2
  data_files:
  - split: test
    path: v2/items_v2.jsonl
  - split: validation
    path: v2/validation_v2.jsonl
---

# StewardBench

A held-out benchmark of a steward's judgement. A steward is a model appointed by a human principal to a team of agents; it reads a team situation and writes one message to the team. Each item gives the principal (name, role, organisation), the principal's standing instructions, the team and what each member is doing, the requests in play, and a gold reply kind, with a gold reply and a contrasting bad reply. It was written for the paper *Borrowed Authority: Can a Small Loyal Commissar Steer Neutral Agents?* (Ephraiem Sarabamoun, Humanity First Research, Apart Swarm Alignment Hackathon, November 2026). All people, organisations and situations are invented.

## Versions

**v1** (`v1/`) has 120 items in ten business domains (customer support, accounts payable, procurement, legal and compliance operations, a university research group, software release, non-clinical clinic administration, warehouse logistics, facilities, and a publishing desk), 12 per domain and 20 per reply kind: an opening brief, restating the principal's instructions, declining a shortcut, questioning an unverified approval, backing a teammate who raises a real problem, and staying quiet. 67 are marked hard, with the reason. The steward's system prompt is `v1/steward_prompt.txt` (a faithful policy).

**v2** (`v2/`) scores a principal-first policy on 150 items (82 hard). Restate items were relabelled as declining a shortcut, and 20 redirect-of-effort items and 10 quiet controls, in which an agent has correctly made one honest attempt for someone else, were added, giving 40 decline-a-shortcut, 30 stay-quiet and 20 each of the other four kinds. Its primary metric is macro accuracy over reply kinds. `v2/steward_prompt_v2.txt`, `_v2_1.txt` and `_v2_2.txt` are the three versions of the steward's instructions that were scored on the same items.

## Judge

A reply is scored by Claude Sonnet 5.5 (`claude-sonnet-5-5`), run as an isolated command-line session with no tools, memory or project instructions. Its system prompt is `v1/judge_system.txt` for both versions; its rubric is `v1/judge_template.txt` for v1 and `v2/judge_template_v2.txt` for v2. The judge returns the reply's kind and flags (for example endorsing a forged approval, claiming authority, inventing an instruction). The items, prompts, judge prompts and scoring code were pinned by sha256 before the judge was validated and before any steward model was scored (`v1/PINS.json`, `v2/PINS_v2*.json`; the judge prompt files here match the pinned hashes). On the 30 validation items the judge agreed with the gold kind on 93.3 percent (Cohen's kappa 0.92) for v1 and 96.7 percent (kappa 0.96) for v2, and an independent blind labeller agreed with the gold kind on 36 of 36 sampled v1 items. A second-party check of the v2 gold labels has not been run.

## Reference results

The base model Qwen3.5-4B (thinking off, temperature 0) scored 58.3 percent [50.0, 66.7] on v1 under the faithful prompt, 60.8 percent [55.4, 66.1] on v2, and 65.3 percent [59.0, 71.7] on v2 under the version 2.1 instructions, with no forged approval endorsed (0 of 20), 5 of 20 real problems backed, and false alarms on 63.3 percent of quiet items. Intervals are item bootstraps.

## Limits

AI agents working under the author's direction wrote the world files the items are built from (`bench/templates/AUTHORING.md` in the source repository), and one judge model scores them, so the benchmark measures agreement with that judge's reading of the gold kinds. The situations are short, English and business-shaped. Only one steward model family has been scored. The pin files had one local path prefix replaced with `<local>/` for this release; nothing else in them changed (see `provenance.json`).

## Licence

Not yet set (`license: other`).

## Citation

```
@misc{sarabamoun2026borrowed,
  title  = {Borrowed Authority: Can a Small Loyal Commissar Steer Neutral Agents?},
  author = {Sarabamoun, Ephraiem},
  year   = {2026},
  note   = {Humanity First Research. Apart Research Swarm Alignment Hackathon}
}
```
