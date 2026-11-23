"""Prints the system's own log of one clean practice case (c0001, first flow, stand-in texts, no AI), with no event and with each
rare event, so that the positions in the group B fault definitions are real. Temporary run folders only."""
import sys, tempfile, json
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from custody import assemble, bench, datasets, store, visits
choices = datasets.default_choices(); wiring = assemble.load_wiring(); rch = bench.run_choices(choices)
case = next(v for v in visits.read_cases(visits.case_path(1, choices), 1) if v.split == "tune")
out = {}
for name, events in (("none", []), ("timeout@w3", [{"on": "timeout", "at": "w3"}]), ("resume@w2", [{"on": "resume", "at": "w2"}])):
    fault = {"fault_id": "LOGS_" + name, "kind": "wiring", "rule": 2, "says": "x", "ops": [], "patch": [], "needs": {}, "events": events}
    with tempfile.TemporaryDirectory() as tmp:
        parts = assemble.make_parts(wiring, rch)
        bench.run_one(case, "A", fault, parts, wiring, choices, tmp)
        log = store.read_store(tmp)["own_log"]
    out[name] = log
    print("== own log, event:", name, "case", case.visit_id)
    for i, x in enumerate(log):
        print(i, x["t"], x["step"], x["action"], x["kind"], x.get("from") or x.get("place"), "->", x.get("to"), x.get("move_id"))
json.dump(out, open(Path(__file__).parent / "clean_logs.json", "w"), indent=1)
