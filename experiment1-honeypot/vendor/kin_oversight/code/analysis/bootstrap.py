"""Item-cluster bootstrap over per-item counts, in pure Python with the stdlib RNG.

The resampling unit is the ITEM (one authored submission), because every monitor, label and
disposition reviews the same items and their rows are correlated through item difficulty.
Resampling is stratified by (author, flawed) so every replicate keeps the design's balance.

The algorithm is pinned so an independent stdlib implementation (``recompute.py``) reproduces
every CI bit for bit:

    rng = random.Random(seed)                      # created once
    for b in range(B):
        for stratum in sorted(strata):             # stratum = (author, flawed)
            ids = sorted(item ids in stratum)
            draws = rng.choices(ids, k=len(ids))   # each draw adds the item's rows once more
        evaluate every estimand on the multiplicity-weighted table

Percentile CI: sort the non-None replicate estimates and take index floor(0.025 * (n - 1)) and
ceil(0.975 * (n - 1)).
"""

import math
import random
from collections import Counter

from .auroc import auroc_from_hist
from .estimands import METRIC_SLOTS, block_keys, blocks_in, evaluate

METHOD = ("item-cluster percentile bootstrap, items resampled with replacement within "
          "(author, flawed) strata; random.Random(seed) created once, strata in sorted order, "
          "rng.choices(sorted_item_ids, k=len(stratum)) per stratum per replicate; CI = sorted "
          "non-None replicates at floor(0.025*(n-1)) and ceil(0.975*(n-1))")


def table_from(items, multiplicity=None):
    """Sum item counts into one table {key: [n_valid, n_flag, aw_w, aw_yes, n_susp, sum_susp, hist]}.

    Each item counts ``multiplicity[item]`` times (default once).
    """
    table = {}
    weights = multiplicity if multiplicity is not None else {item_id: 1 for item_id in items}
    for item_id, times in weights.items():
        for key, cell in items[item_id]["counts"].items():
            total = table.setdefault(key, [0, 0, 0.0, 0.0, 0, 0, {}])
            for slot in range(6):
                total[slot] += times * cell[slot]
            hist = total[6]
            for value, count in cell[6].items():
                hist[value] = hist.get(value, 0) + times * count
    return table


# Block -> expanded table keys. Blocks are immutable, so one expansion serves every replicate.
_KEYS_BY_BLOCK = {}


class RateLookup:
    """Pooled-rate callable over one table (plus ``auroc``), memoising results within that table."""

    def __init__(self, table, items=None, multiplicity=None, units=None):
        """Bind the lookup to one table; items/multiplicity/units serve unit-weighted means."""
        self.table = table
        self.items = items
        self.multiplicity = multiplicity        # None = every item once (the observed table)
        self.units = units if units is not None else {}   # blocks -> {item: unit value}, shared
        self.memo = {}

    def unitmean(self, blocks):
        """Mean over items of each item's unit value, items weighted by their multiplicity (F07, A5).

        A unit is one item: its value in an arm is the mean over the arm's monitors (one block
        each) of that monitor's replicate-pooled rate on the item, so each item counts once per
        arm whatever the number of repeats R.
        """
        if ("unit", blocks) in self.memo:
            return self.memo[("unit", blocks)]
        values = self.units.get(blocks)
        if values is None:
            values = self.units[blocks] = unit_values(self.items, blocks)
        total = weight = 0
        for item_id, value in values.items():
            times = 1 if self.multiplicity is None else self.multiplicity.get(item_id, 0)
            if times:
                total += times * value
                weight += times
        result = total / weight if weight else None
        self.memo[("unit", blocks)] = result
        return result

    def __call__(self, blocks):
        """Return sum(numerator) / sum(denominator) over the blocks' keys, or None when empty."""
        if blocks in self.memo:
            return self.memo[blocks]
        numerator = denominator = 0
        for block in blocks:
            keys = _KEYS_BY_BLOCK.get(block)
            if keys is None:
                keys = _KEYS_BY_BLOCK[block] = block_keys(block)
            num_slot, den_slot = METRIC_SLOTS[block.metric]
            for key in keys:
                cell = self.table.get(key)
                if cell is not None:
                    numerator += cell[num_slot]
                    denominator += cell[den_slot]
        value = numerator / denominator if denominator else None
        self.memo[blocks] = value
        return value

    def auroc(self, block):
        """Suspicion AUROC, flawed vs clean, pooling the block's keys; None when a side is empty."""
        if block in self.memo:
            return self.memo[block]
        keys = _KEYS_BY_BLOCK.get(block)
        if keys is None:
            keys = _KEYS_BY_BLOCK[block] = block_keys(block)
        sides = {True: {}, False: {}}
        for key in keys:
            cell = self.table.get(key)
            if cell is not None:
                side = sides[key[4]]
                for value, count in cell[6].items():
                    side[value] = side.get(value, 0) + count
        value = auroc_from_hist(sides[True], sides[False])
        self.memo[block] = value
        return value


def strata_of(items):
    """Group item ids by (author, flawed); each list sorted."""
    strata = {}
    for item_id, item in items.items():
        strata.setdefault((item["author"], item["flawed"]), []).append(item_id)
    return {key: sorted(ids) for key, ids in strata.items()}


def draw_multiplicities(strata, rng):
    """One bootstrap replicate: how many times each item was drawn."""
    counts = Counter()
    for key in sorted(strata):
        ids = strata[key]
        counts.update(rng.choices(ids, k=len(ids)))
    return counts


def unit_values(items, blocks):
    """{item_id: unit value} for a unit-weighted arm: per item, the mean over blocks (monitors) of
    the block's replicate-pooled rate on that item; items with no valid review are left out."""
    out = {}
    for item_id, item in items.items():
        rates = []
        for block in blocks:
            num_slot, den_slot = METRIC_SLOTS[block.metric]
            num = den = 0
            for key in block_keys(block):
                cell = item["counts"].get(key)
                if cell is not None:
                    num += cell[num_slot]
                    den += cell[den_slot]
            if den:
                rates.append(num / den)
        if rates:
            out[item_id] = sum(rates) / len(rates)
    return out


def replicate_estimates(items, specs, B, seed, units=None):
    """Evaluate every estimand on B resampled tables; returns one list of B values per spec."""
    rng = random.Random(seed)
    strata = strata_of(items)
    values = [[] for _ in specs]
    units = units if units is not None else {}
    for _ in range(B):
        times = draw_multiplicities(strata, rng)
        lookup = RateLookup(table_from(items, times), items, times, units)
        for slot, spec in enumerate(specs):
            values[slot].append(evaluate(spec.expr, lookup))
    return values


def percentile_ci(values):
    """95% percentile interval over non-None replicates: (low, high, n_ok); (None, None, 0) if none."""
    kept = sorted(v for v in values if v is not None)
    if not kept:
        return None, None, 0
    last = len(kept) - 1
    return kept[math.floor(0.025 * last)], kept[math.ceil(0.975 * last)], len(kept)


def items_behind(items, expr):
    """Count distinct items with a non-empty denominator in any block the estimand reads."""
    needed = {(key, METRIC_SLOTS[block.metric][1])
              for block in blocks_in(expr) for key in block_keys(block)}
    return sum(1 for item in items.values()
               if any(cell[slot] > 0 and (key, slot) in needed
                      for key, cell in item["counts"].items() for slot in (0, 2, 4)))
