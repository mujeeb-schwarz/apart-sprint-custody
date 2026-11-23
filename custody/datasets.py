"""Readers of the three public data sets, from data/raw/ (read only).

Field names are the real ones in config/design_choices.json, "data". The three
loaders take the raw folder and return plain dicts with the keys of data.returns.
"""
import ast
import csv
import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from custody.core import DataError

J = Dict[str, Any]
_ROOT = Path(__file__).resolve().parents[1]


def default_choices() -> J:
    path = _ROOT / "config" / "design_choices.json"
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError) as e:
        raise DataError("cannot read %s: %s" % (path, e))


def _read_csv(path: Path) -> List[J]:
    csv.field_size_limit(10 ** 9)
    try:
        with open(str(path), encoding="utf-8", newline="") as f:
            return list(csv.DictReader(f))
    except OSError as e:
        raise DataError("cannot read %s: %s" % (path, e))
    except csv.Error as e:
        raise DataError("malformed csv %s: %s" % (path, e))


def _need(row: J, columns: List[str], where: str) -> None:
    for c in columns:
        if c not in row:
            raise DataError("%s has no column %r" % (where, c))


def load_aci(raw_dir: Any, choices: Optional[J] = None) -> List[J]:
    """207 conversations: files in the order of data.aci.files, each by encounter_id as text."""
    d = (choices or default_choices())["data"]
    base = Path(raw_dir) / d["aci"]["dir"]
    out: List[J] = []
    for fname in d["aci"]["files"]:
        rows = _read_csv(base / fname)
        meta_name = fname[:-4] + d["aci"]["metadata_suffix"]
        meta = {}
        for m in _read_csv(base / meta_name):
            _need(m, d["aci"]["metadata_columns_used"], meta_name)
            meta[m["encounter_id"]] = m
        for r in sorted(rows, key=lambda x: x.get("encounter_id", "")):
            _need(r, d["aci"]["columns"], fname)
            m = meta.get(r["encounter_id"], {})
            other = [s.strip() for s in (m.get("2nd_complaints") or "").split(";") if s.strip()]
            out.append({
                "conversation_id": "aci:" + r["encounter_id"],
                "dialogue": r["dialogue"],
                "note": r["note"],
                "subset": r["dataset"],
                "file": fname,
                "chief_complaint": m.get("cc", ""),
                "other_complaints": other,
            })
    return out


def _grade(certainty: str, answer: str, d: J) -> Optional[str]:
    c = (certainty or "").strip()
    if c:
        return c
    if answer.strip() == d["medevidence"]["no_data_answer"]:
        return "no data"
    return None


def load_medevidence(raw_dir: Any, choices: Optional[J] = None) -> List[J]:
    """284 questions, 263 of them usable, in file order."""
    d = (choices or default_choices())["data"]
    rows = _read_csv(Path(raw_dir) / d["medevidence"]["file"])
    out: List[J] = []
    for r in rows:
        _need(r, d["medevidence"]["columns"], d["medevidence"]["file"])
        try:
            rel = ast.literal_eval(r["relevant_sources"]) if r["relevant_sources"].strip() else []
            src = ast.literal_eval(r["sources"]) if r["sources"].strip() else {}
        except (ValueError, SyntaxError) as e:
            raise DataError("question %s: bad python literal: %s" % (r["question_id"], e))
        sources = []
        for pid in rel:
            s = src.get(str(pid))
            if s is None:
                continue  # a listed id with no entry in 'sources' has no text to show
            article = str(s.get("article_id", pid))
            sources.append({"source_id": "pmid:" + article, "title": s.get("title", ""),
                            "text": s.get("content", ""), "date": s.get("date", "")})
        grade = _grade(r["evidence_certainty"], r["answer"], d)
        out.append({
            "question_id": "medev:" + r["question_id"],
            "question": r["question"],
            "expert_answer": r["answer"],
            "expert_certainty": grade,
            "usable": grade is not None,
            "review": "review:" + r["original_review"],
            "specialty": r["medical_specialty"],
            "fulltext_required": r["fulltext_required"].strip().lower() == "yes",
            "sources": sources,
        })
    return out


def _read_jsonl(path: Path, tolerate_cut_last_line: bool) -> List[J]:
    try:
        with open(str(path), encoding="utf-8") as f:
            lines = [ln for ln in f.read().split("\n") if ln.strip()]
    except OSError as e:
        raise DataError("cannot read %s: %s" % (path, e))
    out = []
    for i, ln in enumerate(lines):
        try:
            out.append(json.loads(ln))
        except ValueError:
            if tolerate_cut_last_line and i == len(lines) - 1:
                continue
            raise DataError("%s line %d is not json" % (path.name, i + 1))
    return out


def load_pocqi(raw_dir: Any, choices: Optional[J] = None) -> List[J]:
    """620 questions with their stored answers by provider; answers are empty when the file is absent."""
    d = (choices or default_choices())["data"]["pocqi"]
    base = Path(raw_dir) / d["dir"]
    questions = _read_jsonl(base / d["questions_file"], False)
    answers: Dict[str, Dict[str, str]] = {}
    apath = base / d["answers_file"]
    if apath.exists():
        for a in _read_jsonl(apath, True):
            if "question_id" not in a or "provider_key" not in a:
                continue
            answers.setdefault(a["question_id"], {})[a["provider_key"]] = a.get(d["answer_text_field"], "")
    out = []
    for q in questions:
        _need(q, d["question_fields"], d["questions_file"])
        out.append({
            "question_id": "pocqi:" + q["question_id"],
            "question": q["question_text"],
            "specialty": q["specialty"],
            "answers": answers.get(q["question_id"], {}),
        })
    return out


def raw_files(raw_dir: Any, choices: Optional[J] = None) -> List[str]:
    """The raw files the loaders read, as paths relative to raw_dir (for the manifest)."""
    d = (choices or default_choices())["data"]
    files = []
    for f in d["aci"]["files"]:
        files.append(d["aci"]["dir"] + "/" + f)
        files.append(d["aci"]["dir"] + "/" + f[:-4] + d["aci"]["metadata_suffix"])
    files.append(d["medevidence"]["file"])
    files.append(d["pocqi"]["dir"] + "/" + d["pocqi"]["questions_file"])
    if (Path(raw_dir) / d["pocqi"]["dir"] / d["pocqi"]["answers_file"]).exists():
        files.append(d["pocqi"]["dir"] + "/" + d["pocqi"]["answers_file"])
    return files
