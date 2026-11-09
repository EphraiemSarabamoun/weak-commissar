---
license: other
license_name: pending-adaption-terms
license_details: "Not yet set. The rows were generated with Adaption Labs' Invent; the licence waits on a reading of Adaption's terms of service."
language:
- en
task_categories:
- text-generation
size_categories:
- 1K<n<10K
tags:
- ai-loyalty
- synthetic
- multi-agent
- supervised-fine-tuning
pretty_name: Commissar steward SFT (v4)
configs:
- config_name: default
  data_files:
  - split: train
    path: data/train.jsonl
  - split: holdout
    path: data/holdout.jsonl
---

# Commissar steward SFT (v4)

Supervised fine-tuning data for a small "commissar": a steward model that sits in a team of AI agents on behalf of one human principal and writes one message to the team, or rewrites a task before an agent reads it. It was built for the paper *Borrowed Authority: Can a Small Loyal Commissar Steer Neutral Agents?* (Ephraiem Sarabamoun, Humanity First Research, Apart Swarm Alignment Hackathon, November 2026), which fine-tunes Qwen3.5-4B on it.

All rows are synthetic. Every person, organisation and situation is invented.

## Format

Each line of `data/train.jsonl` and `data/holdout.jsonl` is `{"prompt": ..., "completion": ...}`. The prompt opens with the steward's instructions (version 2.2 of the principal-first policy, the same prefix in every row, sha256 `92bd5c0f...` in `data/build_report.json`) followed by the team situation; the completion is the steward's one message, or the rewritten task. `data/index.jsonl` has one line per unique row with its split, task (`steward` or `rewrite`), kind and number of copies in the training file.

| Split | Rows | Steward rows | Rewrite rows |
|---|---|---|---|
| train | 1,411 | 1,009 | 402 (134 unique, each repeated three times) |
| holdout | 197 | 176 | 21 |

The rewrite rows are repeated three times in `train.jsonl` on purpose, to weight the rewriting task; deduplicate them if you want each example once. Rows were shuffled with seed 20261108.

## How it was built

Three runs of Adaption Labs' Invent generator produced the raw rows; the dataset prompt of each is in `generation/`.

1. **steward-sft** (1,200 rows) asked for situations across business domains and the steward's reply. It came back skewed toward intervening: in a judged sample of 150, 71 were opening briefs and 67 redirects, and only 4 of all 1,200 completions stayed quiet.
2. **steward-sft-quiet** (400 rows) was a top-up of quiet, back-a-real-problem and approval situations. It came back mostly malformed: 244 replies said "No objection." and then argued the opposite or repeated acknowledgements, 74 glued several replies together, and 23 were clean. An isolated Claude Sonnet 5.5 judge labelled the situations blind, never writing text, and only the 149 high-confidence stay-quiet situations were salvaged, with the completion set to exactly "No objection."; 139 survived the checks. With the rows kept as delivered, 208 top-up rows reached the steward set.
3. **steward-rewrite** (800 rows) asked for a principal's task and its rewrite. Of these, 280 could not be mapped to a shift note and a principal's message; 210 passed the rewriting rules (identifiers, names and dates kept, nothing added, a bounded length), 173 a stricter filter, and 155 a pinned Claude Sonnet 5.5 judge that fails any change of scope, amount, deadline, target or recipient, a dropped request or an added obligation (18 of 173 failed).

Automatic checks then dropped duplicates, contradictory or glued replies, and any row that named a person or organisation from the StewardBench benchmark or from the operae test worlds (6 such hits in 5 rows of the first run). The steward set was rebalanced to about a third opening briefs (35 percent) and split 1,009 train and 176 holdout; the 155 judged rewrites were split 134 and 21.

## Known skews and limits

Opening briefs and redirects dominate (717 of the 1,009 training steward rows). Backing a real problem (14 training rows) and declining a shortcut (9) are thin. The `kind` labels in `index.jsonl` are a judge's for the 150 judged first-run rows and a keyword heuristic for the rest, and 94 training rows are `unclear`. The salvaged quiet rows all share one completion. A judge sample of 100 rewrites found 79 acceptable on fidelity, and the request judge was validated on only 20 hand-labelled pairs, so some rewrites may still add to or change the request. Everything is English, written by one generator, and business-shaped; the instructions in every prompt are one fixed policy. A few rows contain invented email addresses and private network addresses (three addresses and one printer IP, repeated with the rewrite rows) whose domains were not checked for real owners. A later Invent run (steward-rewrite-v5) is not part of this version.

## Intended use

Research on steward or commissar models: training and evaluating a small model that carries one principal's stated priorities into a team's work, and measuring whether it does so faithfully. The holdout split and StewardBench (a separate dataset) are for evaluation.

## Dual use

This is favouritism training. The policy in every prompt tells the steward to put one principal's work first and to give everyone else one honest attempt. The same data could teach a model to serve one person at the expense of colleagues, customers or the public. The policy keeps honesty to others (real attempts, truthful reports, no sabotage), and the paper reports that the favouritism it measured stayed honest, but a deployment should keep the principal's authority verifiable, bound what a principal may ask, and keep honesty to third parties outside the principal's reach. Do not use it to build an agent that deceives or harms people outside the principal's circle.

## Licence

Not yet set (`license: other`). The rows were generated with Adaption Labs' Invent, and the licence will be chosen after Adaption's terms on redistributing generated data have been read.

## Citation

```
@misc{sarabamoun2026borrowed,
  title  = {Borrowed Authority: Can a Small Loyal Commissar Steer Neutral Agents?},
  author = {Sarabamoun, Ephraiem},
  year   = {2026},
  note   = {Humanity First Research. Apart Research Swarm Alignment Hackathon}
}
```
