#!/usr/bin/env python3
"""A fourth forger for the witness test, added by the auditor AFTER the first results were seen.

NOTE: this forger is not part of the decision of 15:03 in night/night_notes.md and had no prediction filed before
the run. It was added on Sun 15 Nov 2026 by the independent audit (ablation/AUDIT.md), after the builder's table.

The fourth forger is the operator (careful record, witness log rewritten with the bench's test key) who also
rebuilds the receipt with the frozen build_receipt, so that record, witness log and receipt agree with one another.
The receipt is rebuilt here independently of the builder's receipt_rebuilt: each forged record i gets as its witness
receipt the rewritten log's entry i (by position, as Ledger.write gives it), and the proof of the old receipt is kept.

It reuses the builder's run_unit, careful, operator_witness and the two checks, and also reruns the clean cases
(both checks) to confirm the second gate. Scratch runs go to a temporary folder outside ablation/.

    python3 ablation/witness_test_forger4.py
"""
import json
import sys
import tempfile
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import witness_test as wt  # noqa: E402
from custody import bench  # noqa: E402
from custody.receipt import build_receipt  # noqa: E402

OUT = HERE / "out" / "results_forger4.json"


def forger4(made, key, wiring, choices):
    orig, edited, wit, old = made["original"], made["careless"], made["witness"], made["receipt"]
    recs = wt.careful(orig, edited)
    log = wt.operator_witness(wit, orig, recs, key)
    assert len(log) == len(recs) and all(e["record_fp"] == r["fp"] for e, r in zip(log, recs))
    with_receipts = [dict(r, receipt=dict(log[i])) for i, r in enumerate(recs)]
    receipt = build_receipt(old["run_id"], wt.CONDITION, with_receipts, old["proof"], wiring, bench.run_choices(choices))
    return recs, log, receipt


def main():
    choices, wiring, planted, pfaults, clean, cfaults, ai = wt.load_inputs()
    key = bench._witness_key(choices)
    parts = dict(wt.assemble.make_parts(wiring, bench.run_choices(choices)))
    parts["ai"] = ai
    work = Path(tempfile.mkdtemp(prefix="forger4_"))
    cells = {c: {"flagged": 0, "missed": 0, "by_edit": {k: {"flagged": 0, "missed": 0} for k in wt.EDIT_KINDS},
                 "problem_kinds": Counter()} for c in wt.CHECKS}
    repro = {f: {c: 0 for c in wt.CHECKS} for f in ("careless", "careful", "operator")}
    for visit in planted:
        made = wt.run_unit(visit, pfaults.get(visit.visit_id), parts, wiring, choices, work)
        kind = wt.edit_kind(visit)
        forged = wt.forge_all(made, key, wiring, choices)
        for f in repro:
            for c, probs in wt.run_checks(*forged[f], key).items():
                repro[f][c] += bool(probs)
        recs, log, receipt = forger4(made, key, wiring, choices)
        for c, probs in wt.run_checks(recs, log, receipt, key).items():
            r = "flagged" if probs else "missed"
            cells[c][r] += 1
            cells[c]["by_edit"][kind][r] += 1
            for p in probs:
                cells[c]["problem_kinds"][wt.kind_of(p)] += 1
    clean_flags = {c: 0 for c in wt.CHECKS}
    for visit in clean:
        made = wt.run_unit(visit, cfaults.get(visit.visit_id), parts, wiring, choices, work)
        for c, probs in wt.run_checks(made["careless"], made["witness"], made["receipt"], key).items():
            clean_flags[c] += bool(probs)
    res = {
        "note": "Added by the auditor after the first results were seen; not in the decision of 15:03 and no "
                "prediction was filed for it. The operator who also rebuilds the receipt with build_receipt.",
        "units_planted": len(planted),
        "forger4_operator_and_receipt": {c: dict(v, problem_kinds=dict(v["problem_kinds"])) for c, v in cells.items()},
        "rerun_of_builder_forgers_flagged": repro,
        "clean_rerun": {"cases": len(clean), "flagged": clean_flags},
    }
    OUT.write_text(json.dumps(res, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(res, indent=1))


if __name__ == "__main__":
    main()
