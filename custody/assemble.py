"""The joiner: binds the five builders' parts together.

Only this file (and the joiner's tools and tests) imports across builders.
"""
import hashlib
import json
from pathlib import Path
from typing import Any, Dict, List

from custody import ai as ai_mod
from custody import datasets, engine, gate, journal, receipt, steps, visits, watch
from custody.core import J

ROOT = Path(__file__).resolve().parents[1]
NOT_RUN = {"status": "not_run", "proven_rules": [], "counterexample": None, "states": None}


def prove(wiring: J) -> J:
    """Tonight's stand-in: the formal tool arrives later, so nothing is proven."""
    return dict(NOT_RUN)


def make_parts(wiring: J, choices: J, hidden_lines: Any = None) -> J:
    """The parts the bench needs. `choices` should be the run choices (no key faults).
    The AI is built from a copy without the keys faults and witness, so nothing it holds
    (its closure included) carries the witness key. `hidden_lines` (bench.hidden_lines_of) are the test split's wordings
    of the hidden line, which only the stand-in gets (it never sees the plan keys)."""
    public = {k: v for k, v in choices.items() if k not in ("faults", "witness")}
    return {
        "steps": steps.STEPS,
        "ai": ai_mod.make_canned_ai(public, hidden_lines),
        "recording_ai": ai_mod.recording_ai,
        "run_visit": engine.run_visit,
        "compose_answer": visits.compose_answer,
        "make_courier": gate.make_courier,
        "review": watch.review,
        "make_ledger": journal.make_ledger,
        "build_receipt": receipt.build_receipt,
        "check_receipt": receipt.check_receipt,
        "prove": prove,
    }


def load_wiring() -> J:
    with open(str(ROOT / "wiring" / "wiring.json"), encoding="utf-8") as f:
        return json.load(f)


def file_fingerprint(path: Any) -> str:
    return hashlib.sha256(Path(str(path)).read_bytes()).hexdigest()


def scorer_fingerprint() -> str:
    h = hashlib.sha256()
    for name in ("core.py", "stats.py", "score.py"):
        h.update((ROOT / "custody" / name).read_bytes())
    return h.hexdigest()


def manifest_fingerprints(choices: J, raw_dir: Any) -> J:
    raw = Path(str(raw_dir))
    data = {rel: file_fingerprint(raw / rel) for rel in datasets.raw_files(raw, choices)}
    prompts = {}
    for pid in sorted(set(p for k, p in choices["prompts"].items() if isinstance(p, str) and len(p) < 40 and " " not in p)):
        pf = ROOT / "prompts" / (pid + ".txt")
        if pf.exists():
            prompts[pid] = file_fingerprint(pf)
    return {
        "wiring": file_fingerprint(ROOT / "wiring" / "wiring.json"),
        "design_choices": file_fingerprint(ROOT / "config" / "design_choices.json"),
        "prompts": prompts,
        "data": data,
        "scorer": scorer_fingerprint(),
    }
