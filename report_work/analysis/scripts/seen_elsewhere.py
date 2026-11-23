"""For each missed planted violation: did the same method raise a flag for another rule in that case?"""
import collections
from common import RUNS, METHODS, COUNTED, jsonl, jload


def missed_seen_elsewhere(run_dir, scores_file):
    sig = collections.defaultdict(list)
    for s in jsonl(run_dir / "signals.jsonl"):
        sig[s["run_id"]].append(s)
    sc = jload(scores_file)
    out = collections.defaultdict(collections.Counter)
    for a in sc["attempts"]:
        if a["part"] != "main" or a["natural"] or a["outcome"] != "missed":
            continue
        rs = {s["rule"] for s in sig[a["run_id"]] if s["by"] in COUNTED[a["condition"]] and s["rule"] not in (0, a["rule"])}
        k = (a["rule"], METHODS[a["condition"]], a["kind"])
        out[k]["missed"] += 1
        out[k]["flag_for_another_rule"] += bool(rs)
        for r in rs:
            out[k]["rule_%d" % r] += 1
    return [{"rule": r, "method": m, "kind": k, **dict(v)} for (r, m, k), v in sorted(out.items())]


if __name__ == "__main__":
    for x in missed_seen_elsewhere(RUNS / "night_e1", RUNS / "night_e1" / "scores.json"):
        print(x)
    for x in missed_seen_elsewhere(RUNS / "night_e2", RUNS / "night_e2_second_pass" / "scores_second_pass.json"):
        print(x)
