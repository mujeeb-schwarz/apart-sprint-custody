"""Is the AI note draft the same under all three methods, and the same as the clean twin's (Experiment 1)?"""
import collections, hashlib, json
from common import RUNS


def check():
    texts = collections.defaultdict(dict)
    visits = {}
    for line in open(RUNS / "night_e1" / "visits.jsonl"):
        v = json.loads(line)
        visits[v["visit_id"]] = v
    for line in open(RUNS / "night_e1" / "texts.jsonl"):
        t = json.loads(line)
        if t["item"]["kind"] != "note_draft":
            continue
        vid, cond = t["run_id"].rsplit(".", 2)[0], t["run_id"].rsplit(".", 2)[1]
        texts[vid][cond] = hashlib.sha256(t["item"]["text"].encode()).hexdigest()
    same_methods = sum(1 for d in texts.values() if len(set(d.values())) == 1)
    twin_same = twin_n = 0
    for vid, d in texts.items():
        tw = visits[vid]["clean_of"]
        if tw and tw in texts and "+r2" not in vid:
            twin_n += 1
            twin_same += d.get("A") == texts[tw].get("A")
    return {"visits_with_draft": len(texts), "same_under_all_methods": same_methods,
            "planted_like_twin": twin_same, "planted_with_twin": twin_n}


if __name__ == "__main__":
    print(check())
