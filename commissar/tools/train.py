"""Launch one AutoScientist SFT (LoRA) run for the commissar (spends credits; needs --yes-spend).

The defaults are the cheapest, fastest configuration the API allows: training_method="instruction",
max_iterations=1, and augmentation_domain_rows=0 / augmentation_general_rows=0 passed explicitly so no
synthetic rows are bought. The API has no price estimate for training (see estimate.py), so before any
spend this script fetches the free recipe AutoScientist would use, prints it, and records it.

Hyperparameters are left to the platform unless an override flag is given (the SDK advises against
overriding). Round 1 under-fitted on the platform recipe (1 epoch at batch_size "max", 23 optimizer
steps), so --n-epochs, --batch-size, --learning-rate, --lora-r and --lora-alpha can replace single
fields. Only the flags given are sent, as the `hyperparams` object; every other field stays the
platform's. Each override is printed beside the recipe value and recorded in hyperparams.json.

Usage:
  .venv/bin/python tools/train.py --dataset-id ds_... [--model Qwen/Qwen3.5-4B]
      [--n-epochs 3] [--batch-size 8|max] [--learning-rate 1e-4] [--lora-r 16 --lora-alpha 32] --yes-spend
"""

from __future__ import annotations

import argparse
import json
import sys
import uuid

import _common

# The override flags and the Hyperparams field each one sets (adaption/types/autoscientist_create_params.py).
HYPERPARAM_FLAGS = {"n_epochs": "--n-epochs", "batch_size": "--batch-size", "learning_rate": "--learning-rate",
                    "lora_r": "--lora-r", "lora_alpha": "--lora-alpha"}


def _positive_float(text: str) -> float:
    value = float(text)
    if not value > 0:
        raise argparse.ArgumentTypeError(f"must be greater than 0, got {text}")
    return value


def _positive_int(text: str) -> int:
    value = int(text)
    if value < 1:
        raise argparse.ArgumentTypeError(f"must be an integer of 1 or more, got {text}")
    return value


def _batch_size(text: str):
    """The SDK's rule: the literal 'max' or an integer of 1 or more (the model's own range is checked by the API)."""
    return "max" if text == "max" else _positive_int(text)


def add_hyperparam_flags(parser: argparse.ArgumentParser) -> None:
    group = parser.add_argument_group("hyperparameter overrides (each replaces one field of the platform recipe)")
    group.add_argument("--n-epochs", type=_positive_float, help="epochs over the training rows (> 0)")
    group.add_argument("--batch-size", type=_batch_size, help="'max' or an integer of 1 or more")
    group.add_argument("--learning-rate", type=_positive_float, help="peak learning rate (> 0)")
    group.add_argument("--lora-r", type=_positive_int, help="LoRA rank (integer of 1 or more)")
    group.add_argument("--lora-alpha", type=_positive_int, help="LoRA alpha: 1x or 2x the rank")


def hyperparam_overrides(args: argparse.Namespace) -> dict:
    """The `hyperparams` body: only the override flags that were given, keyed by the SDK's field names."""
    return {field: getattr(args, field) for field in HYPERPARAM_FLAGS if getattr(args, field, None) is not None}


def check_lora_alpha(overrides: dict, recipe: dict) -> str | None:
    """The SDK's rule that lora_alpha is 1x or 2x lora_r, checked against the rank this run will use (the override,
    else the recipe's). Returns an error message, or None when the pair is valid or alpha is not overridden."""
    if "lora_alpha" not in overrides:
        return None
    rank = overrides.get("lora_r", recipe.get("lora_r"))
    if rank is None:
        return None   # no rank known locally; the API validates against its default
    if overrides["lora_alpha"] not in (rank, 2 * rank):
        return f"--lora-alpha {overrides['lora_alpha']} must be 1x or 2x lora_r ({rank:g}): {rank:g} or {2 * rank:g}"
    return None


def describe_overrides(overrides: dict, recipe: dict) -> list[str]:
    """One line per override flag: the platform's recommended value beside the value this run sends."""
    return [f"  {HYPERPARAM_FLAGS[f]}: recipe {recipe.get(f)!r} -> override {overrides[f]!r}" for f in overrides]


def main() -> int:
    parser = _common.base_parser(__doc__.splitlines()[0], spends=True)
    parser.add_argument("--dataset-id", required=True)
    parser.add_argument("--model", default=_common.DEFAULT_BASE_MODEL)
    parser.add_argument("--max-iterations", type=int, default=1, choices=range(1, 6))
    parser.add_argument("--data-format", default="chat", choices=["chat", "instruction"],
                        help="row encoding for raw datasets (the SDK default is chat)")
    parser.add_argument("--target-win-rate", type=float, default=None)
    parser.add_argument("--voucher", default=None, help="discount voucher code, if Apart or Adaption issued one")
    add_hyperparam_flags(parser)
    args = parser.parse_args()
    overrides = hyperparam_overrides(args)
    try:
        key, client = _common.setup()
    except _common.KeyMissing as exc:
        print(exc)
        return 2
    rec = client.autoscientist.recommend_hyperparams(dataset_id=args.dataset_id, model=args.model,
                                                     augmentation_domain_rows=0, augmentation_general_rows=0)
    recipe = rec.hyperparams.model_dump(exclude_none=True)
    print(f"recipe for {rec.model}: {recipe}")
    error = check_lora_alpha(overrides, recipe)
    if error:
        print(f"refusing: {error}; no paid job was launched")
        return 2
    if overrides:
        print("hyperparameter overrides (sent as `hyperparams`; every other field stays the recipe's):")
        print("\n".join(describe_overrides(overrides, recipe)))
    else:
        print("no hyperparameter overrides: the platform recipe applies unchanged")
    request = {
        "dataset_id": args.dataset_id,
        "model": args.model,
        "training_method": "instruction",
        "data_format": args.data_format,
        "max_iterations": args.max_iterations,
        "augmentation_domain_rows": 0,
        "augmentation_general_rows": 0,
    }
    if args.target_win_rate is not None:
        request["target_win_rate"] = args.target_win_rate
    if args.voucher:
        request["voucher"] = args.voucher
    if overrides:
        request["hyperparams"] = overrides
    print("request: " + json.dumps({k: v for k, v in request.items() if k != "voucher"}, sort_keys=True))
    if not _common.require_spend(args, f"launch training on {args.model}"):
        return 0
    run_dir = _common.new_run_dir("train")
    request["idempotency_key"] = f"commissar-train-{uuid.uuid4().hex}"
    _common.write_json(run_dir / "request.json", {k: v for k, v in request.items() if k != "voucher"}, key)
    _common.write_json(run_dir / "recipe.json", rec, key)
    _common.write_json(run_dir / "hyperparams.json", {"recipe": recipe, "overrides": overrides,
                                                      "effective": {**recipe, **overrides}}, key)
    run = client.autoscientist.create(**request)
    _common.write_json(run_dir / "response.json", run, key)
    print(f"run id={run.id} status={run.status} model={run.model} max_iterations={run.max_iterations}; "
          f"recorded in {run_dir}")
    print(f"next: .venv/bin/python tools/poll.py --run-id {run.id}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
