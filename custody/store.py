"""The store: JSON lines written with canon under runs/<name>/.

Equal inputs give equal bytes, timing.jsonl aside. The plan and the truth sit
under hidden/ and nowhere else. Every open names utf-8.
"""
import json
import os
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from custody.core import J, canon

HIDDEN = "hidden"


def run_path(run_dir: Any, *parts: str) -> Path:
    return Path(str(run_dir)).joinpath(*parts)


def append_jsonl(path: Any, rows: Iterable[Any]) -> None:
    path = Path(str(path))
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(str(path), "a", encoding="utf-8", newline="\n") as fh:
        for row in rows:
            fh.write(canon(row) + "\n")


def write_jsonl(path: Any, rows: Iterable[Any]) -> None:
    path = Path(str(path))
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(str(path), "w", encoding="utf-8", newline="\n") as fh:
        for row in rows:
            fh.write(canon(row) + "\n")


def read_jsonl(path: Any) -> List[Any]:
    path = Path(str(path))
    if not path.exists():
        return []
    out = []
    with open(str(path), "r", encoding="utf-8") as fh:
        for line in fh:
            if line.strip():
                out.append(json.loads(line))
    return out


def write_json(path: Any, obj: Any) -> None:
    path = Path(str(path))
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(str(path), "w", encoding="utf-8", newline="\n") as fh:
        fh.write(canon(obj) + "\n")


def read_json(path: Any) -> Any:
    with open(str(path), "r", encoding="utf-8") as fh:
        return json.load(fh)


def ensure_visit(run_dir: Any, visit: J, fault: Optional[J]) -> None:
    """Add the visit to visits.jsonl and its plan row to hidden/plan.jsonl, once."""
    vp = run_path(run_dir, "visits.jsonl")
    seen = {r.get("visit_id") for r in read_jsonl(vp)}
    if visit["visit_id"] in seen:
        return
    append_jsonl(vp, [visit])
    append_jsonl(run_path(run_dir, HIDDEN, "plan.jsonl"), [{"visit_id": visit["visit_id"], "fault": fault}])


def write_manifest(run_dir: Any, run_name: str, seeds: J, conditions: List[str], counts: J, fingerprints: J,
                   ai: str = "canned", answers_fingerprint: Optional[str] = None,
                   level_source: str = "reader_first") -> None:
    """manifest.json: {run_name, seeds, conditions, counts, fingerprints, ai, answers_fingerprint}. The caller
    computes the fingerprints (the scorer one from the bytes of core.py, stats.py and
    score.py joined in that order). `ai` is "live" (answers written by helpers and kept in live/answers.jsonl,
    whose fingerprint goes in answers_fingerprint) or "canned" (the stand-in text of custody.ai)."""
    if level_source not in ("reader_first", "judge_all"):
        raise ValueError("level_source must be 'reader_first' or 'judge_all'")
    if ai not in ("live", "canned"):
        raise ValueError("ai must be 'live' or 'canned'")
    if ai == "live" and not answers_fingerprint:
        raise ValueError("a live run's manifest needs the fingerprint of its answers file")
    write_json(run_path(run_dir, "manifest.json"), {
        "run_name": run_name, "seeds": seeds, "conditions": list(conditions),
        "counts": counts, "fingerprints": fingerprints, "ai": ai, "answers_fingerprint": answers_fingerprint,
        "level_source": level_source})


def read_store(run_dir: Any) -> Dict[str, Any]:
    """Everything a run folder holds, read back: the plain files, the hidden ones, receipts and journals."""
    root = Path(str(run_dir))
    out: Dict[str, Any] = {}
    for name in ("visits", "results", "signals", "ai_calls", "texts", "own_log", "timing"):
        out[name] = read_jsonl(root / (name + ".jsonl"))
    out["plan"] = read_jsonl(root / HIDDEN / "plan.jsonl")
    out["truth"] = read_jsonl(root / HIDDEN / "truth.jsonl")
    out["receipts"] = {p.name[:-5]: read_json(p) for p in sorted((root / "receipts").glob("*.json"))} \
        if (root / "receipts").exists() else {}
    out["journal"] = {p.name[:-6]: read_jsonl(p) for p in sorted((root / "journal").glob("*.jsonl"))} \
        if (root / "journal").exists() else {}
    out["witness"] = read_jsonl(root / "witness" / "log.jsonl")
    mp = root / "manifest.json"
    out["manifest"] = read_json(mp) if mp.exists() else None
    return out
