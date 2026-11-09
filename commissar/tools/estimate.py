"""Price the two commissar jobs with free calls: an Invent-a-Dataset launch and an SFT training run.

(a) Invent: datasets.invent(dataset_prompt=..., rows=N, estimate=True). Nothing is created or charged;
    the response gives estimated_credits and available_credits.
(b) Training: the API has NO estimate mode for training. In SDK 0.19.0, autoscientist.create takes
    no `estimate` argument and the run object has no credit fields; the only free training call is
    autoscientist.recommend_hyperparams(dataset_id=..., model=...), which needs an existing dataset
    and returns the resolved model and recipe, not a price. So (b) prints that recipe when
    --dataset-id is given, and says plainly that the credit cost is only shown in the Adaption
    app's order summary.

Usage:
  .venv/bin/python tools/estimate.py --prompt-file data/invent_prompt.txt --rows 1200
  .venv/bin/python tools/estimate.py --prompt-file data/invent_prompt.txt --rows 1200 --dataset-id ds_...
"""

from __future__ import annotations

import sys
from pathlib import Path

import _common


def estimate_invent(client, prompt: str, rows: int, training_type: str) -> None:
    """Print the free Invent quote for `rows` rows of the given prompt."""
    est = client.datasets.invent(dataset_prompt=prompt, rows=rows, training_type=training_type, estimate=True)
    print(f"(a) invent {rows} rows ({training_type}): estimated_credits={est.estimated_credits} "
          f"available_credits={est.available_credits} estimate={est.estimate}")


def describe_training(client, dataset_id: str | None, model: str) -> None:
    """Print what the API can say about an SFT run; the credit price is not exposed."""
    print("(b) training: the API exposes no credit estimate for AutoScientist runs "
          "(autoscientist.create has no estimate mode); the app's order summary shows the price.")
    if not dataset_id:
        print("    pass --dataset-id after upload.py to fetch the recipe AutoScientist would use (free).")
        return
    rec = client.autoscientist.recommend_hyperparams(dataset_id=dataset_id, model=model,
                                                     augmentation_domain_rows=0, augmentation_general_rows=0)
    hp = rec.hyperparams
    print(f"    recommended for {rec.model}: training_type={hp.training_type} epochs={hp.n_epochs} "
          f"lr={hp.learning_rate} batch={hp.batch_size} lora_r={hp.lora_r} lora_alpha={hp.lora_alpha}")


def main() -> int:
    parser = _common.base_parser(__doc__.splitlines()[0], spends=False)
    parser.add_argument("--prompt-file", type=Path, required=True, help="text file holding the Invent dataset_prompt")
    parser.add_argument("--rows", type=int, default=1200, help="rows to price (SFT needs at least 1,000)")
    parser.add_argument("--training-type", default="instruction_dataset",
                        choices=["instruction_dataset", "preference_pairs"])
    parser.add_argument("--dataset-id", help="an uploaded dataset, to fetch the training recipe")
    parser.add_argument("--model", default=_common.DEFAULT_BASE_MODEL)
    args = parser.parse_args()
    prompt = args.prompt_file.read_text(encoding="utf-8").strip()
    if len(prompt) > 10_000:
        print(f"prompt is {len(prompt)} characters; Invent accepts at most 10,000")
        return 2
    try:
        _key, client = _common.setup()
    except _common.KeyMissing as exc:
        print(exc)
        return 2
    estimate_invent(client, prompt, args.rows, args.training_type)
    describe_training(client, args.dataset_id, args.model)
    return 0


if __name__ == "__main__":
    sys.exit(main())
