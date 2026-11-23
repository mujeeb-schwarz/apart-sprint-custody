"""Prints the checker's journal of one clean practice case (c0001, stand-in texts, no AI) under B, with no event and with each rare event."""
import sys, tempfile
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from custody import assemble, bench, datasets, store, visits, watch
choices = watch.ai_parts_off(datasets.default_choices()); wiring = assemble.load_wiring(); rch = bench.run_choices(choices)
case = next(v for v in visits.read_cases(visits.case_path(1, choices), 1) if v.split == "test")
for name, events in (("none", []), ("timeout@w3", [{"on": "timeout", "at": "w3"}]), ("resume@w2", [{"on": "resume", "at": "w2"}])):
    fault = {"fault_id": "J_" + name, "kind": "wiring", "rule": 2, "says": "x", "ops": [], "patch": [], "needs": {}, "events": events}
    with tempfile.TemporaryDirectory() as tmp:
        bench.run_one(case, "B", fault, assemble.make_parts(wiring, rch), wiring, choices, tmp)
        j = store.read_store(tmp)["journal"]
        j = list(j.values())[0] if isinstance(j, dict) else j
    print("== journal, event:", name)
    for i, r in enumerate(j):
        h = r["handover"]; print(i, h.get("t"), h.get("action"), h.get("kind"), h.get("from_place"), "->", h.get("to_place"), h.get("move_id"))
