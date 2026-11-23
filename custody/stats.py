"""The one statistic of the custody build: the upper end of an exact binomial interval."""
import math


def _cdf(k, n, p):
    """P(X <= k) for X binomial(n, p), summed in log space with math.lgamma."""
    if k < 0:
        return 0.0
    if k >= n:
        return 1.0
    if p <= 0.0:
        return 1.0
    if p >= 1.0:
        return 0.0
    lp, lq = math.log(p), math.log1p(-p)
    total = 0.0
    for i in range(0, k + 1):
        log_c = math.lgamma(n + 1) - math.lgamma(i + 1) - math.lgamma(n - i + 1)
        total += math.exp(log_c + i * lp + (n - i) * lq)
    return min(1.0, total)


def upper_bound(k, n, tail=0.025):
    """The p at which P(X <= k) equals tail, for X binomial(n, p), by bisection.

    k silent breaks out of n attempts. With k >= n, or with no attempt at all,
    nothing is ruled out and the answer is 1.0.
    """
    if n <= 0 or k >= n:
        return 1.0
    if k < 0:
        k = 0
    lo, hi = 0.0, 1.0
    for _ in range(200):
        mid = (lo + hi) / 2.0
        if _cdf(k, n, mid) > tail:
            lo = mid  # the tail is still too fat, so p must be larger
        else:
            hi = mid
    return (lo + hi) / 2.0


def misses_allowed(n, limit=0.1, tail=0.025):
    """The largest number of misses k among n violations for which the upper end of the two-sided 95% interval
    (upper_bound(k, n)) stays under `limit`. -1 when not even no miss passes (too few violations: no grade)."""
    best = -1
    for k in range(0, n + 1):
        if upper_bound(k, n, tail) < limit:
            best = k
        else:
            break
    return best
