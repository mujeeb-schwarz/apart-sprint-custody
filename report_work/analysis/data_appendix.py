#!/usr/bin/env python3
"""Every number in Appendix J (Data), computed from the data files.

Reads (read-only): config/design_choices.json, data/raw/ (ACI-Bench, medEvidence.csv, real-pocqi),
data/cases/exp1.jsonl and exp2.jsonl, runs/night_e1/visits.jsonl and runs/night_e2/visits.jsonl.
Standard library only; no AI calls, no web requests. Prints the numbers as JSON and writes them to
report_work/analysis/data_appendix_numbers.json.

Run: python3 -I report_work/analysis/data_appendix.py
"""
import ast
import csv
import json
import random
import re
import statistics
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
OUT = HERE / "data_appendix_numbers.json"
csv.field_size_limit(10 ** 9)


def jl(path):
    rows = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def words(text):
    return len(str(text).split())


def spread(values):
    values = list(values)
    if not values:
        return None
    return {"n": len(values), "median": statistics.median(values), "min": min(values), "max": max(values),
            "q1": statistics.quantiles(values, n=4)[0], "q3": statistics.quantiles(values, n=4)[2]}


def non_ascii_share(texts):
    total = sum(len(t) for t in texts)
    odd = sum(sum(1 for ch in t if ord(ch) > 127) for t in texts)
    return round(odd / total, 5) if total else None


cfg = json.load(open(ROOT / "config/design_choices.json", encoding="utf-8"))
raw = ROOT / cfg["data"]["raw_dir"]
N = {}

# ---------------------------------------------------------------- cases as used
exp1 = jl(ROOT / cfg["cases"]["files"]["1"])
exp2 = jl(ROOT / cfg["cases"]["files"]["2"])
N["cases"] = {
    "exp1_total": len(exp1),
    "exp1_by_split": dict(Counter(v["split"] for v in exp1)),
    "exp2_total": len(exp2),
    "exp2_by_kind_and_split": dict(Counter("%s/%s" % (v["meta"]["case_kind"], v["split"]) for v in exp2)),
    "test_total_both": sum(1 for v in exp1 + exp2 if v["split"] == "test"),
}

# ---------------------------------------------------------------- ACI-Bench
aci_cfg = cfg["data"]["aci"]
aci_dir = raw / aci_cfg["dir"]
aci_rows = []
per_file = {}
for fn in aci_cfg["files"]:
    with open(aci_dir / fn, encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    per_file[fn] = len(rows)
    for r in rows:
        r["_file"] = fn
    aci_rows.extend(rows)
meta_names = set()
for fn in aci_cfg["files"]:
    with open(aci_dir / fn.replace(".csv", aci_cfg["metadata_suffix"]), encoding="utf-8", newline="") as f:
        mrows = list(csv.DictReader(f))
    meta_names.update(mrows[0].keys())
aci_by_id = {"aci:" + r["encounter_id"]: r for r in aci_rows}
train_ids = sorted(r["encounter_id"] for r in aci_rows if r["_file"] in cfg["split"]["tune_files"])
expected_practice = {"aci:" + e for e in train_ids[: cfg["split"]["tune_first"]]}
exp1_practice = {v["conversation_id"] for v in exp1 if v["split"] == "tune"}
exp1_test = [v for v in exp1 if v["split"] == "test"]

tag_re = re.compile(r"^\[([a-z_]+)\]")
def turns(dialogue):
    lines = [ln for ln in dialogue.split("\n") if ln.strip()]
    tags = Counter()
    for ln in lines:
        m = tag_re.match(ln.strip())
        tags[m.group(1) if m else "(untagged)"] += 1
    return len(lines), tags

test_tags = Counter()
test_turns, test_words = [], []
for v in exp1_test:
    n, t = turns(v["conversation"])
    test_turns.append(n)
    test_tags.update(t)
    test_words.append(words(v["conversation"]))

N["aci"] = {
    "rows_per_file": per_file,
    "rows_total": len(aci_rows),
    "distinct_encounter_ids": len(aci_by_id),
    "subset_values": dict(Counter(r["dataset"] for r in aci_rows)),
    "metadata_columns": sorted(meta_names),
    "cases_exp1": len(exp1),
    "practice": len(exp1_practice),
    "practice_equals_first_50_of_train_by_id": exp1_practice == expected_practice,
    "practice_first_last": [min(exp1_practice), max(exp1_practice)],
    "test": len(exp1_test),
    "test_by_file": dict(Counter(v["meta"]["file"] for v in exp1_test)),
    "test_by_subset": dict(Counter(v["meta"]["subset"] for v in exp1_test)),
    "left_out": len(aci_rows) - len(exp1),
    "case_text_equals_raw_dialogue": all(aci_by_id[v["conversation_id"]]["dialogue"] == v["conversation"] for v in exp1),
    "test_words": spread(test_words),
    "test_lines_as_turns": spread(test_turns),
    "test_line_tags": dict(test_tags),
    "test_non_ascii_char_share": non_ascii_share([v["conversation"] for v in exp1_test]),
}

# ---------------------------------------------------------------- MedEvidence
me_cfg = cfg["data"]["medevidence"]
with open(raw / me_cfg["file"], encoding="utf-8", newline="") as f:
    me_rows = list(csv.DictReader(f))
def me_usable(r):
    return r["evidence_certainty"].strip() != "" or r["answer"].strip() == me_cfg["no_data_answer"]
usable = [r for r in me_rows if me_usable(r)]
left = [r for r in me_rows if not me_usable(r)]
graded_cases = [v for v in exp2 if v["meta"]["case_kind"] == "graded"]
graded_test = [v for v in graded_cases if v["split"] == "test"]
graded_practice = [v for v in graded_cases if v["split"] == "tune"]
usable_sorted = sorted(usable, key=lambda r: int(r["question_id"]))
first50 = {"medev:" + r["question_id"] for r in usable_sorted[:50]}
N["medevidence"] = {
    "rows": len(me_rows),
    "columns": list(me_rows[0].keys()),
    "certainty_values_raw": dict(Counter(r["evidence_certainty"].strip() or "(empty)" for r in me_rows)),
    "answer_values_raw": dict(Counter(r["answer"].strip() for r in me_rows)),
    "with_grade": sum(1 for r in me_rows if r["evidence_certainty"].strip()),
    "no_grade_insufficient_data": sum(1 for r in me_rows if not r["evidence_certainty"].strip() and r["answer"].strip() == me_cfg["no_data_answer"]),
    "usable": len(usable),
    "left_out_no_grade_other_answer": len(left),
    "left_out_answers": dict(Counter(r["answer"].strip() for r in left)),
    "reviews_in_file": len({r["original_review"] for r in me_rows}),
    "review_year_range": [min(int(r["review_year"]) for r in me_rows if r["review_year"].strip()),
                          max(int(r["review_year"]) for r in me_rows if r["review_year"].strip())],
    "cases_graded": len(graded_cases),
    "practice": len(graded_practice),
    "practice_equals_first_50_usable_by_number": {v["question_id"] for v in graded_practice} == first50,
    "test": len(graded_test),
    "test_reviews": len({v["meta"]["review"] for v in graded_test}),
    "practice_test_share_a_review": len({v["meta"]["review"] for v in graded_test} & {v["meta"]["review"] for v in graded_practice}),
    "test_grade_levels": dict(Counter(str(v["expert_certainty"]) for v in graded_test)),
    "test_expert_answers": dict(Counter(str(v["expert_answer"]) for v in graded_test)),
    "test_studies_per_question": spread([len(v["evidence"]) for v in graded_test]),
    "test_specialties": dict(Counter(v["meta"]["specialty"] for v in graded_test).most_common()),
    "test_non_ascii_char_share_questions": non_ascii_share([v["question"] for v in graded_test]),
}

# ---------------------------------------------------------------- Real-POCQi
pq_cfg = cfg["data"]["pocqi"]
pq_dir = raw / pq_cfg["dir"]
pq_q = jl(pq_dir / pq_cfg["questions_file"])
pq_a = jl(pq_dir / pq_cfg["answers_file"])
pq_r = jl(pq_dir / "ratings__train.jsonl")
provider = pq_cfg["provider"]
stored_by_q = {a["question_id"]: a[pq_cfg["answer_text_field"]] for a in pq_a if a["provider_key"] == provider}
with_stored = sorted(q["question_id"] for q in pq_q if q["question_id"] in stored_by_q)
stored_cases = [v for v in exp2 if v["meta"]["case_kind"] == "stored"]
stored_practice = {v["question_id"].split(":", 1)[1] for v in stored_cases if v["split"] == "tune"}
stored_test = [v for v in stored_cases if v["split"] == "test"]
outside = sorted(q for q in with_stored if q not in stored_practice)
drawn = set(random.Random(cfg["seeds"]["cases"]).sample(outside, cfg["cases"]["stored_test_draw"]))
spec_counter = Counter(v["meta"]["specialty"] for v in stored_test)
top5 = spec_counter.most_common(5)
N["pocqi"] = {
    "questions": len(pq_q),
    "answer_rows": len(pq_a),
    "answer_rows_per_provider_count": len(Counter(a["provider_key"] for a in pq_a)),
    "answer_rows_per_provider": sorted(Counter(a["provider_key"] for a in pq_a).values()),
    "rating_rows": len(pq_r),
    "rating_rows_per_axis": dict(Counter(r["axis"] for r in pq_r)),
    "practice_positions_in_ids_sorted_as_text_1based": [
        min(with_stored.index(q) for q in stored_practice) + 1,
        max(with_stored.index(q) for q in stored_practice) + 1] if stored_practice else None,
    "answer_rows_not_used_other_systems": sum(1 for a in pq_a if a["provider_key"] != provider),
    "questions_with_stored_answer_from_used_tool": len(with_stored),
    "empty_stored_answers": sum(1 for q in with_stored if not str(stored_by_q[q]).strip()),
    "practice": len(stored_practice),
    "outside_practice": len(outside),
    "draw_seed": cfg["seeds"]["cases"],
    "draw_size": cfg["cases"]["stored_test_draw"],
    "test": len(stored_test),
    "test_equals_reproduced_draw": {v["question_id"].split(":", 1)[1] for v in stored_test} == drawn,
    "not_drawn_left_out": len(outside) - len(drawn),
    "case_text_equals_raw_answer": all(v["given_answer"] == stored_by_q[v["question_id"].split(":", 1)[1]] for v in stored_cases),
    "test_answer_words": spread([words(v["given_answer"]) for v in stored_test]),
    "test_question_words": spread([words(v["question"]) for v in stored_test]),
    "test_specialties_distinct": len(spec_counter),
    "test_specialties_top5": top5,
    "test_specialties_other": len(stored_test) - sum(c for _, c in top5),
    "test_specialties_all": dict(spec_counter.most_common()),
    "test_non_ascii_char_share_answers": non_ascii_share([v["given_answer"] for v in stored_test]),
}

# ---------------------------------------------------------------- which cases ran
def ran(path, cases):
    rows = jl(path)
    base = Counter(r["visit_id"].split("+", 1)[0] for r in rows)
    test_ids = {v["visit_id"] for v in cases if v["split"] == "test"}
    tune_ids = {v["visit_id"] for v in cases if v["split"] == "tune"}
    return {
        "rows": len(rows),
        "rows_by_split": dict(Counter(r["split"] for r in rows)),
        "rows_clean_runs": sum(1 for r in rows if "+" not in r["visit_id"]),
        "rows_with_planted_or_repeat_suffix": sum(1 for r in rows if "+" in r["visit_id"]),
        "suffix_prefixes": dict(Counter(r["visit_id"].split("+", 1)[1].split("-")[0] for r in rows if "+" in r["visit_id"])),
        "distinct_cases": len(base),
        "test_cases_that_ran": len(set(base) & test_ids),
        "test_cases_that_did_not_run": len(test_ids - set(base)),
        "practice_cases_that_ran": len(set(base) & tune_ids),
        "clean_run_test_cases": len({r["visit_id"] for r in rows if "+" not in r["visit_id"]} & test_ids),
    }

N["runs"] = {"night_e1": ran(ROOT / "runs/night_e1/visits.jsonl", exp1),
             "night_e2": ran(ROOT / "runs/night_e2/visits.jsonl", exp2)}

text = json.dumps(N, indent=1, ensure_ascii=False, sort_keys=False)
OUT.write_text(text + "\n", encoding="utf-8")
print(text)
