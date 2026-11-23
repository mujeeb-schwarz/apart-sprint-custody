#!/usr/bin/env python3
"""Descriptive counts of the forged logs and of the review's flags on them (no AI call). Writes out/describe.json.

    python3 forger/describe.py
"""
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import lib  # noqa: E402
from lib import OUT, canon  # noqa: E402
from custody import store  # noqa: E402


def shape(true_log, forged):
    t = Counter(canon({k: v for k, v in ln.items() if k != "handover_id"}) for ln in true_log)
    f = Counter(canon({k: v for k, v in ln.items() if k != "handover_id"}) for ln in forged)
    return {"lines_true": len(true_log), "lines_forged": len(forged), "kept_unchanged": sum((t & f).values()),
            "only_in_true": sum((t - f).values()), "only_in_forged": sum((f - t).values()),
            "new_items": len({i for ln in forged for i in (ln.get("item_ids") or [])}
                             - {i for ln in true_log for i in (ln.get("item_ids") or [])}),
            "times_in_order": lib.times_in_order(forged)}


def main() -> int:
    units = {u["visit_id"]: u for u in store.read_jsonl(OUT / "prepared.jsonl")}
    out = {}
    for forger in ("f1", "f2"):
        path = OUT / ("forged_%s.jsonl" % forger)
        if not path.exists():
            continue
        rows = [r for r in store.read_jsonl(path) if r["status"] == "took_effect"]
        shapes = [shape(units[r["visit_id"]]["true_log"], r["forged_log"]) for r in rows]
        sig_path = OUT / ("signals_%s.jsonl" % forger)
        flags = Counter()
        units_with_rule = Counter()
        ai_rule3_reasons = []
        if sig_path.exists():
            for r in store.read_jsonl(sig_path):
                seen = set()
                for s in r["signals"]:
                    flags["%s rule %d" % (s["part"], s["rule"])] += 1
                    seen.add("%s rule %d" % (s["part"], s["rule"]))
                    if s["part"] == "ai" and s["rule"] == 3:
                        ai_rule3_reasons.append({"visit_id": r["visit_id"], "kind": units[r["visit_id"]]["kind"],
                                                 "reason": s["reason"][:300]})
                for k in seen:
                    units_with_rule[k] += 1
        out[forger] = {
            "took_effect": len(rows),
            "mean_lines_forged": round(sum(s["lines_forged"] for s in shapes) / max(1, len(shapes)), 2),
            "units_with_new_items": sum(1 for s in shapes if s["new_items"]),
            "units_with_more_lines_than_true": sum(1 for s in shapes if s["lines_forged"] > s["lines_true"]),
            "units_with_fewer_lines_than_true": sum(1 for s in shapes if s["lines_forged"] < s["lines_true"]),
            "units_times_out_of_order": sum(1 for s in shapes if not s["times_in_order"]),
            "flags_by_part_and_rule": dict(sorted(flags.items())),
            "units_with_a_flag_by_part_and_rule": dict(sorted(units_with_rule.items())),
            "ai_rule3_reasons_sample": ai_rule3_reasons[:12]}
    store.write_json(OUT / "describe.json", out)
    print(json.dumps({f: {k: v for k, v in d.items() if k != "ai_rule3_reasons_sample"} for f, d in out.items()}, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
