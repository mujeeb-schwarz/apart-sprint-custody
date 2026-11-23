"""The visit receipt and the program that checks it.

build_receipt turns the records of one run into the receipt a patient reads.
check_receipt re-derives the receipt from plain journal lines and the witness
log. Both take plain dicts in the JSON form of the files.
"""
import copy
from typing import Any, Dict, List, Optional

from custody.core import ContractError, J
from custody.journal import record_fingerprint
from custody.witness import ZERO_HEAD, chain_head, mac_for

RULES = [1, 2, 3, 4, 5, 6]


def _is_close(rec: J) -> bool:
    return (rec.get("handover") or {}).get("action") == "close"


def _live(records: List[J]) -> List[J]:
    return [r for r in records if not _is_close(r)]


def _broken_rules(rec: J) -> List[int]:
    return [int(v["rule"]) for v in rec.get("verdicts", []) if v.get("verdict") == "broken"]


def _has_verdict(records: List[J], rule: int) -> bool:
    return any(int(v["rule"]) == rule for r in records for v in r.get("verdicts", []))


def _status(records: List[J], rule: int) -> str:
    status = "kept"
    for rec in records:
        if rule in _broken_rules(rec):
            if rec.get("decision") == "block":
                return "blocked"
            status = "flagged"
    return status


def _line_records(records: List[J], rule: int) -> List[int]:
    return [rec["seq"] for rec in records if rule in _broken_rules(rec)]


def build_trail(records: List[J]) -> List[J]:
    """One entry per kind in order of first appearance, from handover.kind."""
    trail: List[J] = []
    index: Dict[str, J] = {}
    for rec in _live(records):
        h = rec["handover"]
        kind = h["kind"]
        if kind not in index:
            index[kind] = {"kind": kind, "went": [], "deleted": {}}
            trail.append(index[kind])
        entry = index[kind]
        if rec.get("decision") == "block":
            continue
        if h.get("action") == "send":
            if not entry["went"]:
                entry["went"].append(h["from_place"])
            entry["went"].append(h["to_place"])
        elif h.get("action") == "delete":
            entry["deleted"].setdefault(h["from_place"], h["t"])
    return trail


def _proven_rules(proof: Optional[J]) -> List[int]:
    if not isinstance(proof, dict) or proof.get("status") != "passed":
        return []
    return [int(r) for r in (proof.get("proven_rules") or [])]


def build_receipt(run_id: str, condition: str, records: List[J], proof: J,
                  wiring: J, choices: J) -> J:
    cond = choices["conditions"].get(condition)
    if cond is None:
        raise ContractError("unknown condition %r" % (condition,))
    records = [copy.deepcopy(r) for r in records]
    live = _live(records)
    checked = set(int(r) for r in choices["guards"]["rules_checked"])
    proven = set(_proven_rules(proof))
    lines = []
    for rule in RULES:
        if condition in ("A", "A+") or rule not in checked:
            status = "not checked"
        else:
            status = _status(live, rule)
        level = "proven" if rule in proven else cond["receipt_level"]
        lines.append({
            "rule": rule,
            "says": choices["receipt"]["says"][str(rule)],
            "level": level,
            "status": status,
            "records": _line_records(live, rule),
        })
    witness_head = ""
    for rec in reversed(records):
        if rec.get("receipt"):
            witness_head = rec["receipt"]["head"]
            break
    return {
        "run_id": run_id,
        "condition": condition,
        "records": records,
        "journal_head": records[-1]["fp"] if records else "",
        "witness_head": witness_head,
        "proof": copy.deepcopy(proof),
        "named_places": [{"place": p["id"], "who": p.get("who", "")}
                         for p in wiring["promise"]["places"] if p.get("named") is True],
        "lines": lines,
        "trail": build_trail(records),
    }


def _strip(rec: J) -> J:
    return {k: v for k, v in rec.items() if k != "receipt"}


def check_receipt(receipt: J, records: List[J], witness_entries: List[J],
                  key=None) -> J:
    """Return {ok, problems}. Never raises on a wrong receipt."""
    problems: List[str] = []
    if isinstance(key, str):
        try:
            key = bytes.fromhex(key.strip())
        except ValueError:
            return {"ok": False, "problems": ["the key is not hex"]}
    try:
        _check(receipt, records, witness_entries, key, problems)
    except (KeyError, TypeError, ValueError, AttributeError) as exc:
        problems.append("malformed input: %s" % (exc,))
    return {"ok": not problems, "problems": problems}


def _check(receipt: J, records: List[J], entries: List[J], key, problems: List[str]) -> None:
    # 1. each record matches its own fingerprint and links to the one before
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

    if records and not _is_close(records[-1]):
        problems.append("the journal does not end with its close record")

    # 2. the witness log chains, and holds each record's fingerprint
    witness_heads: Dict[str, str] = {}
    by_fp: Dict[str, J] = {}
    if records and not entries:
        problems.append("witness off")
        witness_on = False
    else:
        witness_on = True
        head = ZERO_HEAD
        for pos, e in enumerate(entries):
            if e.get("index") != pos:
                problems.append("witness entry %d: its index is %r" % (pos, e.get("index")))
            if e.get("prev_head") != head:
                problems.append("witness entry %d: it does not follow the one before" % pos)
            if e.get("head") != chain_head(e.get("prev_head", ""), e.get("record_fp", "")):
                problems.append("witness entry %d: its head does not match its content" % pos)
            if key is not None and e.get("mac") != mac_for(
                    key, pos, e.get("record_fp", ""), e.get("head", ""), e.get("t")):
                problems.append("witness entry %d: its mac is wrong" % pos)
            head = e.get("head", "")
            by_fp.setdefault(e.get("record_fp"), e)
        for pos, rec in enumerate(records):
            entry = by_fp.get(rec.get("fp"))
            if entry is None:
                problems.append("record %d: the witness holds no fingerprint for it" % pos)
                continue
            held = rec.get("receipt")
            if held and any(held.get(k) != entry.get(k) for k in
                            ("index", "record_fp", "prev_head", "head", "t", "mac")):
                problems.append("record %d: its stored witness receipt differs from the log" % pos)
            witness_heads[rec["fp"]] = entry["head"]

    # 3. the receipt's two heads
    journal_head = records[-1].get("fp") if records else ""
    if receipt.get("journal_head") != journal_head:
        problems.append("the receipt's journal head does not match the journal")
    if witness_on and records:
        want = witness_heads.get(records[-1].get("fp"))
        if want is not None and receipt.get("witness_head") != want:
            problems.append("the receipt's witness head does not match the witness log")
    elif not records and receipt.get("witness_head") not in ("", None):
        problems.append("the receipt's witness head does not match the witness log")

    # 4. the receipt holds these records, and every line follows from them
    if [_strip(r) for r in receipt.get("records", [])] != [_strip(r) for r in records]:
        problems.append("the receipt's records differ from the journal")
    live = _live(records)
    proven = set(_proven_rules(receipt.get("proof")))
    lines = receipt.get("lines", [])
    if [ln.get("rule") for ln in lines] != RULES:
        problems.append("the receipt does not hold one line for each rule")
    else:
        for ln in lines:
            rule = ln["rule"]
            if ln.get("level") not in ("proven", "checked", "promised only"):
                problems.append("rule %d: unknown level %r" % (rule, ln.get("level")))
            if ln.get("level") == "proven" and rule not in proven:
                problems.append("rule %d: marked proven with no passed proof" % rule)
            expected = _status(live, rule)
            if ln.get("status") == "not checked":
                if _has_verdict(live, rule):
                    problems.append("rule %d: marked not checked, but the records checked it" % rule)
                if ln.get("records"):
                    problems.append("rule %d: not checked, yet it lists records" % rule)
                continue
            if ln.get("status") != expected:
                problems.append("rule %d: the status does not follow from the records" % rule)
            if ln.get("records") != _line_records(live, rule):
                problems.append("rule %d: the listed records do not follow from the records" % rule)
    if receipt.get("trail") != build_trail(records):
        problems.append("the trail does not follow from the records")
