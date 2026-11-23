#!/usr/bin/env python3
"""The witness test: what each part of the tamper-evident record adds against an edited record.

    python3 ablation/witness_test.py --out ablation/out

No AI call and no web request. The records are made by the frozen bench (custody.bench.run_one) under Checked (B),
with the AI replaced by the frozen replay of the stored answers of the main run (live_night_e1/answers.jsonl, read
only), as tools/run_advice.py does in its step 2. Each unit runs in its own scratch folder under OUT/work, which is
removed after the unit is read. Nothing outside ablation/ is written.

Three forgers (careless, careful, operator) and two checks (chain alone, chain with the witness). See NOTES.md.
"""
import argparse
import copy
import json
import re
import shutil
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from custody import ai as ai_mod, ai_live, assemble, bench, datasets, store, units, visits  # noqa: E402
from custody.journal import record_fingerprint  # noqa: E402
from custody.receipt import check_receipt, build_receipt  # noqa: E402
from custody.witness import ZERO_HEAD, chain_head, mac_for  # noqa: E402

J = Dict[str, Any]
PLAN = ROOT / "plans" / "test" / "exp1_plan.json"
CATALOGUE = ROOT / "plans" / "test" / "exp1_catalogue.json"
LIVE = ROOT / "live_night_e1"
MAIN_RUN = ROOT / "runs" / "night_e1"
CONDITION = "B"
FORGERS = ("careless", "careful", "operator")
CHECKS = ("chain_alone", "chain_with_witness")
EDIT_KINDS = ("entry_removed", "entry_changed", "entry_added")


# ------------------------------------------------------------------ problem kinds

KIND_PATTERNS = [
    ("record content does not match its fingerprint", r"^record \d+: its content does not match its fingerprint$"),
    ("record does not link to the record before", r"^record \d+: it does not link to the record before it$"),
    ("record sequence number does not follow", r"^record \d+: its sequence number does not follow$"),
    ("journal does not end with its close record", r"^the journal does not end with its close record$"),
    ("witness off", r"^witness off$"),
    ("witness entry index wrong", r"^witness entry \d+: its index is "),
    ("witness entry does not follow the one before", r"^witness entry \d+: it does not follow the one before$"),
    ("witness entry head does not match its content", r"^witness entry \d+: its head does not match its content$"),
    ("witness entry mac wrong", r"^witness entry \d+: its mac is wrong$"),
    ("witness holds no fingerprint for a record", r"^record \d+: the witness holds no fingerprint for it$"),
    ("stored witness receipt differs from the log", r"^record \d+: its stored witness receipt differs from the log$"),
    ("receipt journal head does not match", r"^the receipt's journal head does not match the journal$"),
    ("receipt witness head does not match", r"^the receipt's witness head does not match the witness log$"),
    ("receipt records differ from the journal", r"^the receipt's records differ from the journal$"),
    ("receipt rule line does not follow from the records", r"^rule \d+: "),
    ("receipt lines malformed", r"^the receipt does not hold one line for each rule$"),
    ("receipt trail does not follow from the records", r"^the trail does not follow from the records$"),
    ("malformed input", r"^malformed input: "),
]
CHAIN_KINDS = KIND_PATTERNS[:4]  # the kinds the record alone can show
PART_OF_KIND = {}
for _name, _ in KIND_PATTERNS:
    if _name.startswith("record ") or _name.startswith("journal "):
        PART_OF_KIND[_name] = "chain"
    if _name.startswith("witness") or _name.startswith("stored witness"):
        PART_OF_KIND[_name] = "witness"
    if _name.startswith("receipt"):
        PART_OF_KIND[_name] = "receipt"
PART_OF_KIND["witness holds no fingerprint for a record"] = "witness"
PART_OF_KIND["malformed input"] = "other"


def kind_of(problem: str) -> str:
    for name, pat in KIND_PATTERNS:
        if re.search(pat, problem):
            return name
    return "other: " + problem


def is_chain_kind(problem: str) -> bool:
    return any(re.search(pat, problem) for _, pat in CHAIN_KINDS)


# ------------------------------------------------------------------ the two checks

def chain_alone(records: List[J]) -> List[str]:
    """What the record alone shows, with no witness and no receipt: each record's content against its fingerprint
    (journal.record_fingerprint, the frozen definition), each link against the fingerprint before it, the sequence
    numbers continuous, and the journal ending with its close record. The wording and order are those of
    receipt._check part 1 and its close check, which cannot be called apart from the rest of the frozen check."""
    problems: List[str] = []
    prev_fp = ""
    prev_seq = None
    for pos, rec in enumerate(records):
        if record_fingerprint(rec) != rec.get("fp"):
            problems.append("record %d: its content does not match its fingerprint" % pos)
        if rec.get("prev_fp") != prev_fp:
            problems.append("record %d: it does not link to the record before it" % pos)
        if prev_seq is not None and rec.get("seq") != prev_seq + 1:
            problems.append("record %d: its sequence number does not follow" % pos)
        prev_fp = rec.get("fp")
        prev_seq = rec.get("seq")
    if records and (records[-1].get("handover") or {}).get("action") != "close":
        problems.append("the journal does not end with its close record")
    return problems


def chain_with_witness(receipt: J, records: List[J], witness: List[J], key: bytes) -> List[str]:
    """The bench's full check (custody.receipt.check_receipt), called as bench.run_one step 8 calls it."""
    return list(check_receipt(receipt, records, witness, key)["problems"])


# ------------------------------------------------------------------ the three forgers

def first_touched(original: List[J], edited: List[J]) -> Optional[int]:
    """The first position where the edited record differs from the original one (None when nothing differs)."""
    for i in range(min(len(original), len(edited))):
        if original[i] != edited[i]:
            return i
    if len(original) != len(edited):
        return min(len(original), len(edited))
    return None


# The careless forger is the bench's own planted edit (custody.faults.edit_lines on the journal, bench.run_one step 7),
# nothing else touched; its record is the journal file exactly as step 7 wrote it back (see run_unit).


def careful(original: List[J], edited: List[J]) -> List[J]:
    """The careless edit, then the record made consistent with itself: from the first touched record to the end,
    seq is set to the position, prev_fp to the fingerprint of the record before, and fp computed anew by
    journal.record_fingerprint. The receipt field stays as it is: on disk every journal line holds receipt null
    (journal.py writes the line before the witness is told), so the forger has no copy of a witness receipt to
    keep, and it could not make one without the key; an added record carries null, as the bench's added line does."""
    out = [copy.deepcopy(r) for r in edited]
    start = first_touched(original, edited)
    if start is None:
        return out
    for i in range(start, len(out)):
        rec = out[i]
        rec["seq"] = i
        rec["prev_fp"] = out[i - 1]["fp"] if i > 0 else ""
        rec["fp"] = record_fingerprint(rec)
    return out


def operator_witness(witness: List[J], original: List[J], forged: List[J], key: bytes) -> List[J]:
    """The witness log rewritten to match the forged record, with the bench's test key. The log of a unit's own
    folder holds one entry per record of the original journal, in order (index i is record i). Entries before the
    first touched record are kept; from there on, one new entry per forged record: record_fp its fp, prev_head the
    head before, head = chain_head, t the record's t (as Ledger.write passes it), mac = mac_for with the key."""
    if len(witness) != len(original) or any(e["record_fp"] != r["fp"] for e, r in zip(witness, original)):
        raise RuntimeError("the unit's witness log does not hold one entry per original record")
    start = first_touched(original, forged)
    if start is None:
        return [dict(e) for e in witness]
    out = [dict(e) for e in witness[:start]]
    head = out[-1]["head"] if out else ZERO_HEAD
    for i in range(start, len(forged)):
        fp = forged[i]["fp"]
        t = int(forged[i]["t"])
        new_head = chain_head(head, fp)
        out.append({"index": i, "record_fp": fp, "prev_head": head, "head": new_head, "t": t,
                    "mac": mac_for(key, i, fp, new_head, t)})
        head = new_head
    return out


def receipt_rebuilt(old: J, forged: List[J], witness: List[J], condition: str, wiring: J, choices: J) -> J:
    """Supplementary only (outside the decision): the patient's receipt rebuilt from the forged record, as if the
    operator also held it. Records get their witness receipts from the rewritten log, as the ledger gives them."""
    by_fp = {e["record_fp"]: e for e in witness}
    recs = []
    for r in forged:
        r = dict(r)
        r["receipt"] = dict(by_fp[r["fp"]]) if r["fp"] in by_fp else None
        recs.append(r)
    return build_receipt(old["run_id"], condition, recs, old["proof"], wiring, bench.run_choices(choices))


# ------------------------------------------------------------------ producing the records

def load_inputs() -> Tuple[J, J, List[Any], Dict[str, Optional[J]], List[Any], Dict[str, Optional[J]], Any]:
    choices = datasets.default_choices()
    wiring = assemble.load_wiring()
    every = visits.read_cases(str(visits.case_path(1)), 1)
    plan = units.read_json(str(PLAN), "the plan")
    cat = units.read_json(str(CATALOGUE), "the list of variants")
    planted, pfaults = units.build(plan, "planted", every, choices, cat, None, 3)
    clean, cfaults = units.build(plan, "clean", every, choices, cat, None, None)
    ai = ai_mod.replay_ai(ai_live.replay_rows(ai_live.AnswerStore(LIVE)))
    return choices, wiring, planted, pfaults, clean, cfaults, ai


_KIND_BY_PLANT: Dict[str, str] = {}


def edit_kind(visit: Any) -> Optional[str]:
    """The kind of edit (entry_removed, entry_changed, entry_added), from the plan's row of the unit's plant id."""
    if not _KIND_BY_PLANT:
        for row in units.read_json(str(PLAN), "the plan")["planted"]:
            _KIND_BY_PLANT[row["plant_id"]] = row["kind"]
    pid = (visit.meta.get("unit") or {}).get("plant_id")
    return _KIND_BY_PLANT.get(pid) if pid else None


def run_unit(visit: Any, fault: Optional[J], parts: J, wiring: J, choices: J, work: Path) -> J:
    """One bench run under Checked in a fresh folder; returns the original journal, the careless journal (as the
    bench left it), the witness log, the receipt and whether it crashed."""
    run_dir = work / visit.visit_id.replace("+", "_")
    if run_dir.exists():
        shutil.rmtree(str(run_dir))
    try:
        res = bench.run_one(visit, CONDITION, fault, parts, wiring, choices, run_dir)
        rid = res.run_id
        edited = store.read_jsonl(store.run_path(run_dir, "journal", rid + ".jsonl"))
        witness = store.read_jsonl(store.run_path(run_dir, "witness", "log.jsonl"))
        receipt = store.read_json(store.run_path(run_dir, "receipts", rid + ".json"))
        signals = [s for s in store.read_jsonl(store.run_path(run_dir, "signals.jsonl")) if s.get("by") == "ledger"]
    finally:
        if run_dir.exists():
            shutil.rmtree(str(run_dir))
    # the journal as the ledger wrote it: the receipt's records (built at step 6, before the edit) with receipt null,
    # which is the form Ledger.write puts on disk
    original = [dict(r, receipt=None) for r in receipt["records"]]
    return {"run_id": rid, "crashed": bool(res.crashed), "original": original, "careless": edited,
            "witness": witness, "receipt": receipt, "bench_ledger_reasons": [s["reason"] for s in signals]}


def forge_all(made: J, key: bytes, wiring: J, choices: J) -> Dict[str, Tuple[List[J], List[J], J]]:
    """(records, witness log, receipt) as each forger leaves them."""
    orig, edited, wit, rec = made["original"], made["careless"], made["witness"], made["receipt"]
    car = careful(orig, edited)
    op_w = operator_witness(wit, orig, car, key)
    out = {"careless": (edited, wit, rec), "careful": (car, wit, rec), "operator": (car, op_w, rec)}
    out["operator_and_receipt"] = (car, op_w, receipt_rebuilt(rec, car, op_w, CONDITION, wiring, choices))
    return out


def run_checks(records: List[J], witness: List[J], receipt: J, key: bytes) -> Dict[str, List[str]]:
    return {"chain_alone": chain_alone(records),
            "chain_with_witness": chain_with_witness(receipt, records, witness, key)}


# ------------------------------------------------------------------ main

def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(ROOT / "ablation" / "out"))
    ap.add_argument("--limit", type=int, default=None, help="only the first n units of each set (for a dry loop)")
    a = ap.parse_args(argv)
    out = Path(a.out).resolve()
    if ROOT / "ablation" not in out.parents and out != ROOT / "ablation":
        raise SystemExit("--out must be inside ablation/")
    work = out / "work"
    work.mkdir(parents=True, exist_ok=True)

    choices, wiring, planted, pfaults, clean, cfaults, ai = load_inputs()
    if a.limit:
        planted, clean = planted[:a.limit], clean[:a.limit]
    key = bench._witness_key(choices)
    parts = dict(assemble.make_parts(wiring, bench.run_choices(choices)))
    parts["ai"] = ai

    lines: List[J] = []
    table = {f: {c: {"flagged": 0, "missed": 0, "by_edit": {k: {"flagged": 0, "missed": 0} for k in EDIT_KINDS},
                     "problem_kinds": Counter(), "problem_parts": Counter(), "units_with_part": Counter()} for c in CHECKS}
             for f in FORGERS + ("operator_and_receipt",)}
    gate1 = {"units": 0, "flagged_full_check": 0, "flagged_main_run": 0, "same_flag": 0, "same_reasons": 0,
             "journal_same_as_main_run": 0, "journal_compared": 0, "differences": []}
    crashed: List[str] = []

    for visit in planted:
        fault = pfaults.get(visit.visit_id)
        kind = edit_kind(visit)
        made = run_unit(visit, fault, parts, wiring, choices, work)
        if made["crashed"]:
            crashed.append(made["run_id"])
        forged = forge_all(made, key, wiring, choices)
        for forger, (recs, wit, rec) in forged.items():
            res = run_checks(recs, wit, rec, key)
            for check, problems in res.items():
                cell = table[forger][check]
                flagged = bool(problems)
                cell["flagged" if flagged else "missed"] += 1
                cell["by_edit"][kind]["flagged" if flagged else "missed"] += 1
                for p in problems:
                    cell["problem_kinds"][kind_of(p)] += 1
                    cell["problem_parts"][PART_OF_KIND.get(kind_of(p), "other")] += 1
                for part in sorted({PART_OF_KIND.get(kind_of(p), "other") for p in problems}):
                    cell["units_with_part"][part] += 1
                lines.append({"set": "planted", "unit": visit.visit_id, "run_id": made["run_id"], "edit": kind,
                              "fault_id": (fault or {}).get("fault_id"), "forger": forger, "check": check,
                              "result": "flagged" if flagged else "missed", "problems": problems,
                              "supplementary": forger == "operator_and_receipt"})
        made["full_careless"] = run_checks(made["careless"], made["witness"], made["receipt"], key)
        gate1["units"] += 1
        gate1["flagged_full_check"] += 1 if made["full_careless"]["chain_with_witness"] else 0
        gate1.setdefault("_pending", []).append((made["run_id"], made["full_careless"]["chain_with_witness"],
                                                 made["bench_ledger_reasons"], made["careless"]))

    # the main run's ledger signals and journals, read once (read only)
    pending = gate1.pop("_pending", [])
    wanted = {rid for rid, _, _, _ in pending}
    main_reasons: Dict[str, List[str]] = {rid: [] for rid in wanted}
    with open(str(MAIN_RUN / "signals.jsonl"), encoding="utf-8") as fh:
        for ln in fh:
            if '"ledger"' not in ln:
                continue
            s = json.loads(ln)
            if s.get("by") == "ledger" and s.get("run_id") in wanted:
                main_reasons[s["run_id"]].append(s["reason"])
    for rid, mine, bench_reasons, journal in pending:
        theirs = main_reasons.get(rid, [])
        gate1["flagged_main_run"] += 1 if theirs else 0
        gate1["same_flag"] += 1 if bool(mine) == bool(theirs) else 0
        same = Counter(mine) == Counter(theirs)
        gate1["same_reasons"] += 1 if same else 0
        jp = MAIN_RUN / "journal" / (rid + ".jsonl")
        if jp.exists():
            gate1["journal_compared"] += 1
            if store.read_jsonl(jp) == journal:
                gate1["journal_same_as_main_run"] += 1
            else:
                gate1["differences"].append({"run_id": rid, "what": "journal differs from the main run's"})
        if not same:
            gate1["differences"].append({"run_id": rid, "what": "problems differ", "mine": mine, "main_run": theirs})
        if Counter(bench_reasons) != Counter(mine):
            gate1["differences"].append({"run_id": rid, "what": "the bench's own ledger signals differ from the check"})

    gate2 = {"cases": 0, "with_problem": {c: 0 for c in CHECKS}, "problems": [], "main_run_ledger_flags": 0}
    clean_ids = []
    for visit in clean:
        made = run_unit(visit, cfaults.get(visit.visit_id), parts, wiring, choices, work)
        if made["crashed"]:
            crashed.append(made["run_id"])
        clean_ids.append(made["run_id"])
        gate2["cases"] += 1
        if made["careless"] != made["original"]:
            gate2["problems"].append({"run_id": made["run_id"], "what": "the journal on disk differs from the receipt's records"})
        res = run_checks(made["careless"], made["witness"], made["receipt"], key)
        for check, problems in res.items():
            if problems:
                gate2["with_problem"][check] += 1
                gate2["problems"].append({"run_id": made["run_id"], "check": check, "problems": problems})
            lines.append({"set": "clean", "unit": visit.visit_id, "run_id": made["run_id"], "edit": None,
                          "forger": "none", "check": check, "result": "flagged" if problems else "clean",
                          "problems": problems, "supplementary": False})
    cids = set(clean_ids)
    with open(str(MAIN_RUN / "signals.jsonl"), encoding="utf-8") as fh:
        for ln in fh:
            if '"ledger"' in ln:
                s = json.loads(ln)
                if s.get("by") == "ledger" and s.get("run_id") in cids:
                    gate2["main_run_ledger_flags"] += 1

    n_planted = len(planted)
    gate1_held = (gate1["flagged_full_check"] == n_planted and gate1["same_flag"] == n_planted and n_planted == 100)
    gate2_held = (gate2["cases"] == len(clean) and all(v == 0 for v in gate2["with_problem"].values())
                  and not gate2["problems"] and len(clean) == 157)
    if a.limit:
        gate1_held = gate1_held if n_planted == 100 else None
        gate2_held = gate2_held if len(clean) == 157 else None

    results = {
        "what": "the witness test (ablation): three forgers by two checks on the rule 3 record edits under Checked",
        "units_planted": n_planted, "cases_clean": len(clean), "crashed_runs": crashed,
        "edits_by_kind": dict(Counter(edit_kind(v) for v in planted)),
        "table": {f: {c: {"flagged": table[f][c]["flagged"], "missed": table[f][c]["missed"],
                          "by_edit": table[f][c]["by_edit"],
                          "problem_kinds": dict(sorted(table[f][c]["problem_kinds"].items())),
                          "problem_parts": dict(sorted(table[f][c]["problem_parts"].items())),
                          "units_with_a_problem_of_part": dict(sorted(table[f][c]["units_with_part"].items()))}
                      for c in CHECKS} for f in FORGERS},
        "supplementary_operator_and_receipt": {
            "note": "outside the decision: the operator also rebuilds the patient's receipt from the forged record",
            "table": {c: {"flagged": table["operator_and_receipt"][c]["flagged"],
                          "missed": table["operator_and_receipt"][c]["missed"],
                          "problem_kinds": dict(table["operator_and_receipt"][c]["problem_kinds"])} for c in CHECKS}},
        "clean": {"cases": gate2["cases"], "with_problem": gate2["with_problem"],
                  "main_run_ledger_flags_on_these_cases": gate2["main_run_ledger_flags"]},
        "gate1": dict(gate1, held=gate1_held),
        "gate2": dict(gate2, held=gate2_held),
    }
    out.mkdir(parents=True, exist_ok=True)
    (out / "results.json").write_text(json.dumps(results, indent=2, sort_keys=False) + "\n", encoding="utf-8")
    with open(str(out / "units.jsonl"), "w", encoding="utf-8") as fh:
        for row in lines:
            fh.write(json.dumps(row, sort_keys=True) + "\n")
    if work.exists() and not any(work.iterdir()):
        work.rmdir()
    print("planted %d, clean %d, crashed %d" % (n_planted, len(clean), len(crashed)))
    for f in FORGERS:
        print("%-10s chain alone %3d/%d   with witness %3d/%d" % (
            f, table[f]["chain_alone"]["flagged"], n_planted, table[f]["chain_with_witness"]["flagged"], n_planted))
    print("gate 1 held: %s   gate 2 held: %s" % (gate1_held, gate2_held))
    return 0 if (gate1_held is not False and gate2_held is not False) else 4


if __name__ == "__main__":
    sys.exit(main())
