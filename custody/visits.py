"""The cases of Version 2: one list of conversations (Experiment 1) and one of questions (Experiment 2).

The joined "visit" (a conversation paired with a question, `build_visits`) is retired: the two flows never
meet. `build_visits` stays only to rebuild the retired list, from which the practice sets of the two lists
are read, so that nothing moves between practice and test. The class `Visit` and its field names are kept.
"""
import json
import random
from dataclasses import asdict
from pathlib import Path
from typing import Any, Dict, List

from custody.core import Visit, DataError, ContractError, canon
from custody import datasets

J = Dict[str, Any]
ROOT = Path(__file__).resolve().parents[1]


def _tune_ids(convs: List[J], choices: J) -> set:
    split = choices["split"]
    rows = [c["conversation_id"] for c in convs if c["file"] in split["tune_files"]]
    return set(sorted(rows)[: split["tune_first"]])


def _question_pool(raw_dir: Any, choices: J) -> List[J]:
    d = choices["data"]
    med = [q for q in datasets.load_medevidence(raw_dir, choices) if q["usable"]]
    med.sort(key=lambda q: int(q["question_id"].split(":", 1)[1]))
    provider = d["pocqi"]["provider"]
    poc = [q for q in datasets.load_pocqi(raw_dir, choices) if provider in q["answers"]]
    poc.sort(key=lambda q: q["question_id"].split(":", 1)[1])
    return [dict(q, _kind="med") for q in med] + [dict(q, _kind="poc") for q in poc]


def _make_visit(i: int, c: J, q: J, tune: set, provider: str) -> Visit:
    med = q["_kind"] == "med"
    meta = {
        "subset": c["subset"], "file": c["file"],
        "chief_complaint": c["chief_complaint"], "other_complaints": c["other_complaints"],
        "specialty": q["specialty"], "review": q["review"] if med else None,
    }
    return Visit(
        visit_id="v%04d" % (i + 1),
        conversation_id=c["conversation_id"],
        conversation=c["dialogue"],
        question_id=q["question_id"],
        question=q["question"],
        evidence=[{"source_id": s["source_id"], "title": s["title"], "text": s["text"]}
                  for s in q["sources"]] if med else [],
        expert_answer=q["expert_answer"] if med else None,
        expert_certainty=q["expert_certainty"] if med else None,
        given_answer=None if med else q["answers"][provider],
        given_by=None if med else provider,
        split="tune" if c["conversation_id"] in tune else "test",
        matched=False,
        meta=meta,
    )


def build_visits(n: int, choices: J, raw_dir: Any) -> List[Visit]:
    """RETIRED joined list: the first n visits in visit order (fewer when the questions or conversations run out)."""
    if n < 0:
        raise ContractError("n must not be negative")
    convs = datasets.load_aci(raw_dir, choices)
    pool = _question_pool(raw_dir, choices)
    tune = _tune_ids(convs, choices)
    cap = choices["visits"]["per_conversation_max"]
    walk = list(convs) + list(reversed(convs))  # second walk in reverse order
    if cap < 2:
        walk = list(convs)
    provider = choices["data"]["pocqi"]["provider"]
    return [_make_visit(i, walk[i], pool[i], tune, provider) for i in range(min(n, len(pool), len(walk)))]


# ------------------------------------------------------------------ the two lists of cases

def practice_sets(choices: J, raw_dir: Any) -> J:
    """What today's joined list (retired) puts in practice: conversation ids, graded question ids, stored question ids."""
    tune = [v for v in build_visits(choices["visits"]["total"], choices, raw_dir) if v.split == "tune"]
    return {"conversations": {v.conversation_id for v in tune},
            "graded": {v.question_id for v in tune if v.expert_certainty is not None},
            "stored": {v.question_id for v in tune if v.expert_certainty is None}}


def build_cases(choices: J, raw_dir: Any) -> J:
    """{1: [Visit], 2: [Visit]}. Experiment 1: the 207 transcripts, c0001 on, in the data's order. Experiment 2: the 263
    graded questions, the 36 stored-answer questions of the practice set and `cases.stored_test_draw` stored-answer
    questions drawn by lot (seeds.cases) from those outside the practice set, q0001 on, in the data's order."""
    c = choices["cases"]
    practice = practice_sets(choices, raw_dir)
    provider = choices["data"]["pocqi"]["provider"]
    exp1 = []
    for i, conv in enumerate(datasets.load_aci(raw_dir, choices)):
        exp1.append(Visit(
            visit_id="c%04d" % (i + 1), conversation_id=conv["conversation_id"], conversation=conv["dialogue"],
            question_id="", question="", evidence=[], expert_answer=None, expert_certainty=None,
            given_answer=None, given_by=None,
            split="tune" if conv["conversation_id"] in practice["conversations"] else "test", matched=False,
            meta={"subset": conv["subset"], "file": conv["file"], "chief_complaint": conv["chief_complaint"],
                  "other_complaints": conv["other_complaints"], "case_kind": "transcript"},
            experiment=1))
    pool = _question_pool(raw_dir, choices)
    graded = [q for q in pool if q["_kind"] == "med"]
    stored = [q for q in pool if q["_kind"] == "poc"]
    outside = sorted(q["question_id"] for q in stored if q["question_id"] not in practice["stored"])
    drawn = set(random.Random(choices["seeds"]["cases"]).sample(outside, c["stored_test_draw"]))
    keep = [q for q in graded] + [q for q in stored if q["question_id"] in practice["stored"] or q["question_id"] in drawn]
    exp2 = []
    for i, q in enumerate(keep):
        med = q["_kind"] == "med"
        pr = q["question_id"] in (practice["graded"] if med else practice["stored"])
        exp2.append(Visit(
            visit_id="q%04d" % (i + 1), conversation_id="", conversation="",
            question_id=q["question_id"], question=q["question"],
            evidence=[{"source_id": s["source_id"], "title": s["title"], "text": s["text"]} for s in q["sources"]] if med else [],
            expert_answer=q["expert_answer"] if med else None,
            expert_certainty=q["expert_certainty"] if med else None,
            given_answer=None if med else q["answers"][provider], given_by=None if med else provider,
            split="tune" if pr else "test", matched=False,
            meta={"specialty": q["specialty"], "review": q["review"] if med else None,
                  "case_kind": "graded" if med else "stored"},
            experiment=2))
    return {1: exp1, 2: exp2}


def _one_line(text: str) -> str:
    return " ".join(str(text).split())


def compose_answer(visit: Visit, choices: J) -> Any:
    """The text of the answer as it enters the advice flow (version 3); None for a case that has no question.

    A stored-answer question: the stored answer, then the source tag that names the tool, then the AI mark.
    A graded question: a program writes the answer in fixed wording from the experts' conclusion, their grade
    and the studies (config: data.composed_answer): the question, one claim line with the source tag, the
    studies' titles and the AI mark. No AI writes either text."""
    markers = choices["markers"]
    tag = markers["source_tag"]
    if visit.given_answer is not None:
        source = "tool:%s" % visit.given_by
        return "%s\n%s %s%s\n%s" % (visit.given_answer.rstrip("\n"), tag["open"], source, tag["close"], markers["ai"])
    if visit.expert_certainty is None or visit.expert_answer is None:
        return None
    cfg = choices["data"]["composed_answer"]
    try:
        answer_phrase = cfg["answer_phrases"][visit.expert_answer]
        certainty_phrase = cfg["certainty_phrases"][visit.expert_certainty]
    except KeyError as exc:
        raise ContractError("no wording in data.composed_answer for %s" % exc)
    ids = list(dict.fromkeys(e["source_id"] for e in visit.evidence))  # one id once, even when a study is listed twice
    source_tag = "%s %s%s" % (tag["open"], (tag["separator"] + " ").join(ids), tag["close"])
    titles = cfg["title_separator"].join(_one_line(e["title"])[:cfg["title_cut"]] for e in visit.evidence)
    lines = [
        cfg["question_line"].format(question=_one_line(visit.question)),
        cfg["claim_line"].format(claim=markers["claim"], answer_phrase=answer_phrase,
                                 certainty_phrase=certainty_phrase, source_tag=source_tag),
        cfg["studies_line"].format(n=len(visit.evidence), titles=titles),
        markers["ai"],
    ]
    return "\n".join(lines)


def case_path(experiment: int, choices: Any = None) -> Path:
    name = ((choices or {}).get("cases") or {}).get("files", {}).get(str(experiment)) or "data/cases/exp%d.jsonl" % experiment
    return ROOT / name


def read_cases(path: Any, experiment: int) -> List[Visit]:
    """A case file; every case must carry the experiment asked for."""
    out = read_visits(path)
    bad = [v.visit_id for v in out if v.experiment != experiment]
    if bad:
        raise DataError("%s holds cases that are not of experiment %d: %s" % (path, experiment, ", ".join(bad[:5])))
    return out


def case_counts(cases: List[Visit]) -> J:
    """Counts of one list: by split and by graded / stored (an Experiment 1 case is a transcript)."""
    out: J = {"cases": len(cases)}
    for split in ("tune", "test"):
        sub = [v for v in cases if v.split == split]
        out[split] = len(sub)
        for kind in ("transcript", "graded", "stored"):
            k = sum(1 for v in sub if v.meta.get("case_kind") == kind)
            if k:
                out["%s_%s" % (split, kind)] = k
    return out


def visit_counts(visits: List[Visit]) -> J:
    """The four counts the tool prints, plus the two conversation counts."""
    tune = [v for v in visits if v.split == "tune"]
    test = [v for v in visits if v.split == "test"]
    graded = lambda vs: sum(1 for v in vs if v.expert_certainty is not None)
    return {
        "visits": len(visits),
        "tune_visits": len(tune), "tune_graded": graded(tune),
        "test_visits": len(test), "test_graded": graded(test),
        "tune_conversations": len({v.conversation_id for v in tune}),
        "test_conversations": len({v.conversation_id for v in test}),
    }


def write_visits(path: Any, visits: List[Visit]) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(str(p), "w", encoding="utf-8") as f:
        for v in visits:
            f.write(canon(asdict(v)) + "\n")


def read_visits(path: Any) -> List[Visit]:
    try:
        with open(str(path), encoding="utf-8") as f:
            lines = [ln for ln in f.read().split("\n") if ln.strip()]
    except OSError as e:
        raise DataError("cannot read %s: %s" % (path, e))
    out = []
    for i, ln in enumerate(lines):
        try:
            out.append(Visit(**json.loads(ln)))
        except (ValueError, TypeError) as e:
            raise DataError("%s line %d: %s" % (path, i + 1, e))
    return out
