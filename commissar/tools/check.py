"""Verify the Adaption key with free calls only, and show what we can train and what we can spend.

Calls made:
  autoscientist.list_models()  -> GET /api/v1/autoscientist/models (read-only)
  datasets.invent(..., estimate=True)  -> POST /api/v1/datasets/invent with estimate=true. The SDK
      documents estimate mode as "Price the request without creating or charging anything", and
      its response carries `available_credits`, which is the only balance field the API exposes.
      Skip it with --no-balance.

Usage:  .venv/bin/python tools/check.py [--no-balance]
"""

from __future__ import annotations

import sys

import _common


def print_models(client) -> None:
    """Print every trainable base model with its size, methods and training types."""
    response = client.autoscientist.list_models()
    print(f"trainable base models ({len(response.models)}):")
    for m in response.models:
        size = m.api_model_size or "?"
        print(f"  {m.id:55s} size={size:>6s} methods={','.join(m.methods)} types={','.join(m.training_types)}")
    ids = {m.id for m in response.models}
    flag = "available" if _common.DEFAULT_BASE_MODEL in ids else "NOT in the list"
    print(f"default base model {_common.DEFAULT_BASE_MODEL}: {flag}")


def print_balance(client) -> None:
    """Read the credit balance from a free 10-row Invent estimate (nothing is created or charged)."""
    est = client.datasets.invent(
        dataset_prompt="Balance probe: short instruction-response pairs about agent governance.",
        rows=10,
        estimate=True,
    )
    print(f"credit balance (available_credits): {est.available_credits}")
    print(f"  (probe estimate for 10 rows: {est.estimated_credits} credits; estimate={est.estimate})")


def main() -> int:
    parser = _common.base_parser(__doc__.splitlines()[0], spends=False)
    parser.add_argument("--no-balance", action="store_true", help="skip the free estimate that reads the balance")
    args = parser.parse_args()
    try:
        _key, client = _common.setup()
    except _common.KeyMissing as exc:
        print(exc)
        return 2
    print(f"base url: {client.base_url}")
    print_models(client)
    if not args.no_balance:
        print_balance(client)
    return 0


if __name__ == "__main__":
    sys.exit(main())
