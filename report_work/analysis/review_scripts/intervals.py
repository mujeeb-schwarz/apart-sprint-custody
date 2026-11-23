"""Check the analyst's interval numbers and add the exact McNemar tests on paired discordant counts (reviewer's own code)."""
import json, math, sys
from recompute import cp, allowed
checks = {"FA 0/157": cp(0, 157), "FA 1/157": cp(1, 157), "FA 52/207": cp(52, 207), "FA 1/412": cp(1, 412),
          "FA 0/413": cp(0, 413), "FA 0/207": cp(0, 207), "miss 1/62": cp(1, 62), "miss 0/62": cp(0, 62),
          "miss 8/62": cp(8, 62), "miss 2/7": cp(2, 7), "miss 4/7": cp(4, 7), "miss 1/8 (rule 4 wrong source, Monitored)": cp(1, 8),
          "miss 12/100": cp(12, 100), "miss 60/100": cp(60, 100), "miss 37/157 rule0 warn on clean e1": cp(37, 157),
          "allowed": {n: allowed(n) for n in (36, 53, 54, 62, 69, 70, 84, 85, 99, 100, 113, 168)}}
def mcnemar_exact(b, c):
    n = b + c
    if n == 0:
        return 1.0
    k = min(b, c)
    p = sum(math.comb(n, i) for i in range(k + 1)) / 2 ** n
    return min(1.0, 2 * p)
pairs = {"e1 r1 Monitored vs Promised": (67, 0), "e1 r2 Checked vs Monitored": (33, 0), "e1 r3 Checked vs Monitored": (12, 0),
         "e2 r4 Monitored vs Promised": (7, 0), "e2 r4 Checked vs Monitored": (1, 0), "e2 r5 Checked vs Monitored": (0, 3),
         "e2 r6 Monitored vs Promised": (60, 0), "e2 r6 Checked vs Monitored": (0, 0)}
checks["mcnemar_exact_p"] = {k: mcnemar_exact(*v) for k, v in pairs.items()}
json.dump(checks, sys.stdout, indent=1)
