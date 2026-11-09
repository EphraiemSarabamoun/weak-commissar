"""AUROC of suspicion scores, flawed (positive) against clean (negative), from value histograms.

AUROC = P(s_flawed > s_clean) + 0.5 * P(s_flawed == s_clean), the Mann-Whitney statistic divided
by n_flawed * n_clean. Suspicion is an integer 0-100, so both groups are kept as {value: count}
histograms; that makes the statistic cheap to recompute on every bootstrap table. The numerator is
accumulated in integer half-units, so the result is one exact division (bit-reproducible).
"""


def auroc_from_hist(flawed, clean):
    """AUROC from two {value: count} histograms; None when either group is empty."""
    n_flawed, n_clean = sum(flawed.values()), sum(clean.values())
    if not n_flawed or not n_clean:
        return None
    twice_wins = 0          # 2 * (pairs with flawed > clean) + (tied pairs)
    clean_below = 0         # clean scores strictly below the current value
    for value in sorted(set(flawed) | set(clean)):
        at_flawed, at_clean = flawed.get(value, 0), clean.get(value, 0)
        twice_wins += at_flawed * (2 * clean_below + at_clean)
        clean_below += at_clean
    return twice_wins / (2 * n_flawed * n_clean)
