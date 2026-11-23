"""Recomputes the counts of the sealed ideas from night/ideas/ideas_tally.json (no text, no AI call, no model run).

    python3 night/ideas/tally_ideas.py

An idea counts as missed by a method when any of its cases that took effect was missed; it took effect under a
method when at least one case did not end in did_not_fire (the rule of ideas_run.md, section 2)."""
import json
from collections import Counter
from pathlib import Path

ideas = json.loads((Path(__file__).parent / "ideas_tally.json").read_text())["ideas"]
print("ideas:", len(ideas), dict(sorted(Counter(i["group"] for i in ideas).items())))
b = [i for i in ideas if i["group"] == "B"]
print("new and plantable (group B):", len(b), "ran:", sum(i["ran"] for i in b))
def took(i, m): return any(o != "did_not_fire" for o in i["outcomes"][m])
def missed(i, m): return any(o == "missed" for o in i["outcomes"][m])
for m in ("Promised", "Monitored", "Checked"):
    t = [i for i in b if took(i, m)]
    print("%-9s took effect %d, missed %d" % (m, len(t), sum(missed(i, m) for i in t)))
r3 = [i for i in b if i["rule"] == 3]
print("rule 3 ideas in group B:", len(r3), "missed by Promised:", sum(missed(i, "Promised") for i in r3),
      "missed by Monitored:", sum(missed(i, "Monitored") for i in r3))
