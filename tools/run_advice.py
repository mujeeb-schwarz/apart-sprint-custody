#!/usr/bin/env python3
"""The advice half, with live AI answers produced by helpers outside the program.

The program has no API key and never calls a model. It works in rounds:

    python3 tools/run_advice.py run      works out the AI calls it still needs, writes the missing
                                         ones (each with its call id and its full prompt) and stops;
                                         with nothing missing it runs the bench, has the judge read
                                         the texts, and scores
    (helpers answer the calls, writing lines {"call_id", "prompt_fp", "output"} to a file)
    python3 tools/run_advice.py import FILE [FILE ...]
                                         checks each answer against the prompt it claims and stores it
    python3 tools/run_advice.py run      again, until nothing is missing
    python3 tools/run_advice.py export   only works out the missing chain calls and writes them
    python3 tools/run_advice.py status   counts the stored answers and the pending calls

The missing calls go out in three separate sets, never mixed, so that a helper who plays an AI step
never reads the checkers' prompts. Give each set to its own helpers:
    live/handout/pending_steps.jsonl     note_writer, plan, patient_note
    live/handout/pending_methods.jsonl   watcher and reviewer
    live/handout/pending_judge.jsonl     judge
each with --batch-size parts in live/handout/pending_steps_parts/, pending_methods_parts/, pending_judge_parts/.
Give helpers live/handout/ and nothing else: never live/, never the project. The salt, the token map and the
map from each exported call id to the real call are in live/private/ and stay with the program. A call id
in the handout is made only from the prompt as shown, so it says nothing about the visit or the condition.
Inside a set the calls are in a seeded shuffle (seeds.export_order), so neighbours come from different
visits. Import takes answers for any of the three sets. A watcher or reviewer answer is either the single
line NO FLAGS or only lines FLAG <rule number> <reason>; anything else, an empty answer too, is refused
and the call stays pending. A step answer that is empty or a refusal
is stored as given, marked usable false, and its visit is left out of the scores
(runs/<name>/unusable_visits.json). The old single live/pending.jsonl is no longer written; if a folder
holds one, export again.

By plan (version 3): --plan PLAN.json --part clean|planted|kept_copy|hidden|repeat [--rule N] runs the units of one
part of a plan made by tools/make_plan.py. A unit is one case with at most one planted violation, run under each method
asked for; its id is the case id (clean) or <case>+<plant id> (+r2 added for the repeat check). One run folder holds
every part: a later call with the same --name and --live-dir and another part adds its units and never recomputes or
changes a unit that is complete (all its methods have a result). An Experiment 1 plan takes its violations from the
list of variants beside it (exp1_catalogue.json, or --catalogue FILE); an Experiment 2 plan's planted and repeat parts
take theirs from --faults FILE (tools/make_plan.py faults-exp2). The run's --split must be the plan's split.

Every answer is kept in live/answers.jsonl, so a finished run can be scored again with no AI at all.
Tuning visits only, unless --split test or --split all says otherwise. A selection that holds a test
visit (--split all counts) runs only after tools/file_predictions.py has filed the owner's predictions and the
filed page still matches; the first such run freezes every prompt, the design choices and the scorer in
live/frozen.json, and a later one refuses a change unless --after-freeze-change "<reason>" is given. Exit code: 0 nothing missing,
3 calls are still missing (a normal stop), 1 an import refused some answers, 2 a bad input.
"""
import argparse
import functools
import json
import os
import shutil
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from custody import ai as ai_mod, ai_live, assemble, bench, datasets, faults, filing, judge, score, score_parts, store, units, visits, watch  # noqa: E402
from custody.core import AICallMissing, ContractError, CustodyError, canon, fingerprint  # noqa: E402

SPLITS = {"tune": ["tune"], "test": ["test"], "all": ["tune", "test"]}
WAITING = 3


# ------------------------------------------------------------------ setup

def select(vs, split):
    """The visits of the chosen split. Tuning and test visits never mix unless the split is 'all'."""
    return [v for v in vs if v.split in SPLITS[split]]


def plan_extras(a):
    """The files a run by plan uses, as freeze items (filing.EXTRA): the plan, the list of variants and the Experiment 2
    faults file. Each is taken when a stage first uses it and refused later if it differs."""
    out = {}
    if getattr(a, "plan", None):
        out["plan"] = filing._sha(a.plan)
        if a.experiment == 1:
            cat = Path(a.catalogue) if a.catalogue else Path(a.plan).resolve().parent / "exp1_catalogue.json"
            if cat.exists():
                out["catalogue"] = filing._sha(cat)
        if getattr(a, "faults", None) and Path(a.faults).exists():
            out["faults"] = filing._sha(a.faults)
    return out


def guard(a, choices, chosen):
    """The wall around the test visits (custody.filing.guard): a selection with a test visit needs filed
    predictions that still match, and freezes (or checks) every prompt, the design choices, the scorer and
    the visit list (its fingerprint). --filing-dir works only with CUSTODY_TESTING=1; so does a --visits file
    other than the project's own, for every selection, not only one with a test visit (14 Nov, H5; J4)."""
    testing = os.environ.get("CUSTODY_TESTING") == "1"
    if a.filing_dir and not testing:
        raise CustodyError("--filing-dir is only for the project's own tests: it is honoured only when the "
                           "environment variable CUSTODY_TESTING is set to 1")
    has_test = any(v.split == "test" for v in chosen)
    own = visits.case_path(a.experiment, choices)
    if not testing and Path(a.visits).resolve() != own.resolve():
        raise CustodyError("a run on real answers must use the project's own %s for every selection "
                           "(--visits points to %s); a changed visit list could relabel tuning and test visits"
                           % (own, a.visits))
    filing.guard(has_test, a.live_dir, choices, a.after_freeze_change, a.filing_dir, a.visits, plan_extras(a))


def plan_units(a, choices, every):
    """The units of one part of a plan (custody.units.build): (units, faults by unit id)."""
    if not a.part:
        raise CustodyError("--plan needs --part clean, planted, kept_copy, hidden or repeat")
    if a.part == "clean" and a.rule:
        raise CustodyError("--rule with --part clean is refused: it shrinks the clean cases that the false-alarm rate is made from")
    plan = units.read_json(a.plan, "the plan")
    if plan.get("experiment") != a.experiment:
        raise CustodyError("the plan is of experiment %s, not %s" % (plan.get("experiment"), a.experiment))
    if plan.get("split") != a.split:
        raise CustodyError("the plan is of the split %s: run it with --split %s" % (plan.get("split"), plan.get("split")))
    cat = None
    if a.experiment == 1:
        path = Path(a.catalogue) if a.catalogue else Path(a.plan).resolve().parent / "exp1_catalogue.json"
        cat = units.read_json(path, "the list of variants")
    f2 = units.read_json(a.faults, "the faults file") if a.faults else None
    if a.experiment == 2 and a.part in ("planted", "repeat") and f2 is None:
        raise CustodyError("part %s of an Experiment 2 plan needs --faults FILE (tools/make_plan.py faults-exp2)" % a.part)
    return units.build(plan, a.part, every, choices, cat, f2, a.rule)


def setup(a):
    if (a.part or a.rule or a.catalogue or a.faults) and not a.plan:
        raise CustodyError("--part, --rule, --catalogue and --faults go with --plan")
    if a.plan and (a.trial or a.sealed):
        raise CustodyError("--plan takes the cases by plan: leave out --trial and --sealed")
    if a.sealed and a.split != "test":
        raise CustodyError("--sealed plants the outside writer's faults, so it needs --split test")
    choices = datasets.default_choices()
    if a.ai_parts == "off":
        choices = watch.ai_parts_off(choices)
    wiring = assemble.load_wiring()
    rchoices = bench.run_choices(choices)  # once; goes to make_parts
    every = visits.read_cases(a.visits, a.experiment)
    if a.plan:  # version 3: the units of one part of a plan; a unit is a case with at most one planted violation
        chosen, plan = plan_units(a, choices, every)
        if a.limit:
            chosen = chosen[:a.limit]
        guard(a, choices, chosen)
        conds = a.conditions.split(",") if a.conditions else choices["conditions"]["order"]
        return choices, wiring, rchoices, chosen, plan, conds, []
    if a.trial:  # N clean practice cases plus the practice violations of this experiment, each on its own case
        if a.split != "tune" or a.limit or a.sealed:
            raise CustodyError("--trial takes the practice set by itself: leave out --split, --limit and --sealed")
        chosen, plan, _clean, unplaced = faults.plan_trial(
            every, faults.load_practice_faults(a.experiment, choices), a.trial, choices, wiring)
        guard(a, choices, chosen)
    else:
        fl = faults.load_faults(choices, ROOT, include_sealed=a.sealed)
        plan_all, unplaced = faults.plan_faults_report(every, fl, choices, wiring)  # planned over every case, so a subset
        chosen = select(every, a.split)                                              # keeps the faults the full set gives it
        if a.limit:
            chosen = chosen[:a.limit]
        guard(a, choices, chosen)
        plan = {v.visit_id: plan_all.get(v.visit_id) for v in chosen}
    conds = a.conditions.split(",") if a.conditions else choices["conditions"]["order"]
    return choices, wiring, rchoices, chosen, plan, conds, unplaced


def prompt_ids(choices):
    p = choices["prompts"]
    return p["watcher"], p["reviewer"], p["judge"]


def split_flags_answer(output):
    """(the FLAG and NO FLAGS lines joined, the other non-empty lines) of a monitor or review answer (15 Nov,
    lenient import). A line goes with the flags when it is a FLAG line, holds FLAG with a number, or is NO FLAGS;
    any other line is kept apart and never changes a flag (watch.parse_flags reads FLAG lines only)."""
    flags, extra = [], []
    for ln in (output or "").splitlines():
        s = watch.strip_lead(ln)
        if not ln.strip():
            continue
        if watch._FLAG_LINE.match(s) or watch._FLAG_WORD.search(s) or s.rstrip(" \t*_`.").casefold() == watch._NO_FLAGS:
            flags.append(ln)
        else:
            extra.append(ln)
    return "\n".join(flags), extra


def validate_flags_answer_lenient(output, call=None):
    """watch.validate_flags_answer on the FLAG and NO FLAGS lines only; with neither, the answer stays refused."""
    flags, extra = split_flags_answer(output)
    if extra and not flags:
        raise ContractError("the answer has no line FLAG <rule number> <reason> and no NO FLAGS")
    watch.validate_flags_answer(flags, call)


# --------------------------------------------------- finding the missing calls

def visit_tokens(live_dir, choices):
    """The opaque visit tokens for the checkers' prompts (watcher, reviewer, judge); salt in live/private/."""
    p = choices["prompts"]
    return ai_live.VisitTokens(live_dir, [p["watcher"], p["reviewer"], p["judge"]])


def template_fp(prompt_id):
    """The fingerprint of a prompt's template, one of the three things an exported call id is made from."""
    return fingerprint(ai_mod.prompt_text(prompt_id))


def find_chain_calls(chosen, plan, conds, choices, wiring, rchoices, answers, scratch, tokens):
    """Run every visit under every condition against the stored answers; return the collector and the
    number of runs that stopped for a missing step text or crashed for another reason."""
    watcher, reviewer, judge_id = prompt_ids(choices)
    collector = ai_live.Collector()
    live = ai_live.discovering_ai(answers, collector, ai_mod.render_prompt, ai_mod.call_id_of,
                                  placeholder_for={watcher: "", reviewer: ""},
                                  expects_of=functools.partial(judge.expects_of, judge_prompt=judge_id),
                                  mask=tokens.mask, template_fp_of=template_fp)
    parts = dict(assemble.make_parts(wiring, rchoices))
    parts["ai"] = live
    stopped = crashed = 0
    if scratch.exists():
        shutil.rmtree(str(scratch))
    try:
        for visit in chosen:
            for cond in conds:
                live.set_case(ai_live.case_of(visit.visit_id))
                try:
                    res = bench.run_one(visit, cond, plan.get(visit.visit_id), parts, wiring, choices, scratch)
                    crashed += 1 if res.crashed else 0
                except AICallMissing:
                    stopped += 1
                finally:
                    live.set_case(None)
    finally:
        if scratch.exists():
            shutil.rmtree(str(scratch))
    tokens.save()
    return collector, stopped, crashed


def find_judge_calls(run_dir, choices, answers, tokens, level_source="reader_first"):
    """The judge's calls for a finished run: one for each (item, rule) the readers cannot read, and the
    marked sample. Returns (collector, judge rows, sample rows, jobs, sample jobs, visits by id)."""
    watcher, reviewer, judge_id = prompt_ids(choices)
    judge_choices = choices
    texts = store.read_jsonl(run_dir / "texts.jsonl")
    vmap = {v["visit_id"]: v for v in store.read_jsonl(run_dir / "visits.jsonl")}
    jobs = judge.build_jobs(texts, vmap, judge_choices, level_source=level_source)
    # the marked sample comes from the visits of the run in hand (a tuning run gets one too)
    sample = judge.sample_jobs(texts, vmap, judge_choices, splits=sorted({v["split"] for v in vmap.values()}),
                               level_source=level_source)
    collector = ai_live.Collector()
    live = ai_live.discovering_ai(answers, collector, ai_mod.render_prompt, ai_mod.call_id_of,
                                  placeholder_for={judge_id: ""},
                                  expects_of=functools.partial(judge.expects_of, judge_prompt=judge_id),
                                  mask=tokens.mask, template_fp_of=template_fp)
    rows = judge.judge_jobs(live, jobs, judge_choices, lenient=True)
    srows = judge.judge_jobs(live, sample, judge_choices, lenient=True)
    tokens.save()
    return collector, rows, srows, jobs, sample, vmap


# ------------------------------------------------------------- the commands

LEGACY_MESSAGE = ("%s holds an old pending.jsonl. That single file mixed step calls with checker calls and is "
                  "no longer written or read. Export again: python3 tools/run_advice.py export")


def legacy_check(live_dir, move):
    """Say plainly when a folder still holds the old pending.jsonl. With move true (a command that
    exports anyway) the old file is renamed to pending.jsonl.old; otherwise the command stops."""
    old = ai_live.legacy_pending(live_dir)
    if old is None:
        return
    if not move:
        raise CustodyError(LEGACY_MESSAGE % live_dir)
    print("note: " + LEGACY_MESSAGE % live_dir)
    print("the old file is moved to %s; the new files follow" % (str(old) + ".old"))
    old.replace(str(old) + ".old")


def split_by_set(calls, choices):
    by_set = {name: [] for name in ai_live.SETS}
    for c in calls:
        by_set[ai_live.set_of(c["prompt_id"], choices["live"]["export_sets"])].append(c)
    return by_set


def export(live_dir, calls, batch_size, choices):
    """Write the missing calls as three separate sets, each shuffled; returns {set: path}."""
    by_rule = lambda c: "r%s" % judge.rule_of_prompt(c["prompt"], choices)  # noqa: E731  (the judge's parts, per rule)
    return ai_live.export_sets(live_dir, split_by_set(calls, choices), choices["seeds"]["export_order"], batch_size,
                               part_key={"judge": by_rule})


def report_missing(calls, paths, stage, choices):
    by = Counter(c["prompt_id"] for c in calls)
    ids = sum(len(c.get("real") or [c["call_id"]]) + len(c["also"]) for c in calls)
    print("%s: %d AI calls are missing (%s); %d call ids, since calls that show one prompt share an answer" % (
        stage, len(calls), ", ".join("%s %d" % kv for kv in sorted(by.items())), ids))
    for name, group in split_by_set(calls, choices).items():
        if group:
            print("  %s: %d calls, written to %s" % (name, len(group), paths[name]))
    print("give each set to its own helpers. Answer each call with one line {\"call_id\", \"prompt_fp\", \"output\"} "
          "in a file, then: python3 tools/run_advice.py import FILE")


def answers_fingerprint(live_dir):
    """sha256 of live/answers.jsonl: the answers a live run was made from (an empty file when there is none)."""
    path = Path(live_dir) / "answers.jsonl"
    return fingerprint(path.read_text(encoding="utf-8")) if path.exists() else fingerprint("")


def write_unusable(run_dir, st, choices, live_dir):
    """runs/<name>/unusable_visits.json: each visit that had an empty step answer or a confirmed refusal, with the
    step, the call id, the reason and the first 300 characters of the answer. The scorer leaves these visits out of
    every count. runs/<name>/refusal_candidates.json: every step answer that holds a refusal phrase in its first
    200 characters, listed once (at the answer that first holds the phrase in its visit, not at later texts that
    only repeat it), with the visit, step, call id, first 300 characters and `confirmed`. A candidate is confirmed
    only when its call id is in live/private/unusable_confirmed.json, a file a person keeps: it is created empty
    when missing and never rewritten here (J1, 14 Nov). Both files are always written (possibly empty)."""
    bad = st.unusable()  # empty answers
    confirmed = set(ai_live.read_confirmed(live_dir))
    outputs = {r["call_id"]: r["output"] for r in st.rows()}
    steps = list(choices["live"]["export_sets"]["steps"])
    step_names = set(steps)
    candidate = ai_live.make_candidate_test(choices)
    rows = []
    for row in store.read_jsonl(run_dir / "ai_calls.jsonl"):
        step = row["prompt_id"].rsplit(".v", 1)[0]
        rows.append((row["run_id"].split(".")[0], steps.index(step) if step in step_names else 99, step, row["call_id"]))
    rows.sort()
    seen, cands, earlier = {}, {}, {}  # earlier: visit -> outputs of the steps already passed
    for vid, rank, step, cid in rows:
        key = (vid, cid)
        out = outputs.get(cid, "")
        if cid in bad:
            seen.setdefault(key, {"visit_id": vid, "step": step, "call_id": cid, "reason": bad[cid],
                                  "first_300": out[:300]})
        elif step in step_names and cid in outputs:
            phrase = candidate(out)
            if phrase:
                at = _norm_text(out).index(phrase)
                snippet = _norm_text(out)[at:at + 40]
                echo = any(snippet in _norm_text(o) for o in earlier.get(vid, []))
                if cid in confirmed:
                    seen.setdefault(key, {"visit_id": vid, "step": step, "call_id": cid, "reason": "refusal",
                                          "first_300": out[:300]})
                if not echo:
                    cands.setdefault(key, {"visit_id": vid, "step": step, "call_id": cid,
                                           "reason": "refusal phrase in the first 200 characters: %s" % phrase,
                                           "first_300": out[:300], "confirmed": cid in confirmed})
        elif cid in confirmed:
            seen.setdefault(key, {"visit_id": vid, "step": step, "call_id": cid, "reason": "refusal",
                                  "first_300": out[:300]})
        if cid in outputs:
            earlier.setdefault(vid, []).append(out)
    order = lambda r: (r["visit_id"], r["call_id"])  # noqa: E731
    store.write_json(run_dir / "unusable_visits.json", sorted(seen.values(), key=order))
    store.write_json(run_dir / "refusal_candidates.json", sorted(cands.values(), key=order))


def _norm_text(text):
    return text.replace("\u2019", "'").replace("\u2018", "'").casefold()


def incomplete(run_dir, chosen, conds):
    """[(unit, methods it still lacks)] for the units of a plan run that are not complete in the run folder. A unit
    has a result for a method when results.jsonl holds one (a crashed run is a result too). Nothing is changed."""
    done: dict = {}
    for r in store.read_jsonl(Path(run_dir) / "results.jsonl"):
        if r.get("rep", 0) == 0:
            done.setdefault(r["visit_id"], set()).add(r["condition"])
    out = []
    for v in chosen:
        missing = [c for c in conds if c not in done.get(v.visit_id, set())]
        if missing:
            out.append((v, missing))
    return out


def check_plan_folder(run_dir, conds, split=None):
    """A run folder that holds earlier parts keeps its methods and its split: another list of methods, or a manifest that
    names another split, is refused."""
    mp = Path(run_dir) / "manifest.json"
    if mp.exists():
        man = store.read_json(mp)
        had = (man.get("counts") or {}).get("split")
        if split and had and had != split:
            raise CustodyError("%s was made on the split %s; this call is on %s: use another --name" % (run_dir, had, split))
        have = man.get("conditions")
        if have != list(conds):
            raise CustodyError("%s was made for the methods %s; this call asks for %s. One run folder holds one list of "
                               "methods: use another --name" % (run_dir, ",".join(have or []), ",".join(conds)))


def prior_parts(run_dir):
    mp = Path(run_dir) / "manifest.json"
    if not mp.exists():
        return []
    return list(((store.read_json(mp).get("counts") or {}).get("plan_parts_run")) or [])


def prior_stages(run_dir):
    mp = Path(run_dir) / "manifest.json"
    return list(store.read_json(mp).get("stages") or []) if mp.exists() else []


def cmd_run(a):
    choices, wiring, rchoices, chosen, plan, conds, unplaced = setup(a)
    live_dir = Path(a.live_dir)
    runs_dir = Path(a.runs_dir)
    legacy_check(live_dir, True)
    levels = a.levels or choices["rules"].get("level_source", "reader_first")
    st = ai_live.AnswerStore(live_dir)
    answers = st.answers()
    print("%s visits (%s): %d, conditions %s, %d stored answers" % (
        a.split, ", ".join(sorted({v.split for v in chosen})) or "none", len(chosen), ",".join(conds), len(answers)))
    if unplaced and a.split != "tune":
        print("faults no visit could take: %s" % ", ".join(unplaced))
    run_dir = runs_dir / a.name
    todo = incomplete(run_dir, chosen, conds) if a.plan else [(v, list(conds)) for v in chosen]
    if a.plan:
        print("plan %s, part %s%s: %d units, %d to run, %d complete already" % (
            a.plan, a.part, (", rule %d" % a.rule) if a.rule else "", len(chosen), len(todo), len(chosen) - len(todo)))
        check_plan_folder(run_dir, conds, a.split)
    # 1. the chain
    collector, stopped, crashed = find_chain_calls([v for v, _ in todo], plan, conds, choices, wiring, rchoices, answers,
                                                   ai_live.private_dir(live_dir) / "_scratch", visit_tokens(live_dir, choices))
    if crashed:
        print("warning: %d runs crashed while the calls were being worked out" % crashed)
    if len(collector):
        paths = export(live_dir, collector.rows(), a.batch_size, choices)
        report_missing(collector.rows(), paths, "chain", choices)
        print("%d of the %d runs wait on a missing text" % (stopped, len(chosen) * len(conds)))
        return WAITING
    # 2. the bench, with stored answers only
    parts = dict(assemble.make_parts(wiring, rchoices))
    parts["ai"] = ai_mod.replay_ai(ai_live.replay_rows(st))
    if a.plan:  # a later part adds its units to the folder; a complete unit is never run again
        groups: dict = {}
        for v, missing in todo:
            groups.setdefault(tuple(missing), []).append(v)
        for missing, vs in groups.items():
            bench.run_all(vs, list(missing), plan, parts, wiring, choices, run_dir)
    else:
        if run_dir.exists():
            shutil.rmtree(str(run_dir))
        bench.run_all(chosen, conds, plan, parts, wiring, choices, run_dir)
    counts = visits.case_counts(chosen)
    counts["experiment"] = a.experiment
    counts["ai_parts"] = a.ai_parts
    counts["faults_planned"] = sum(1 for f in plan.values() if f)
    if a.plan:
        counts["plan_parts_run"] = sorted(set(prior_parts(run_dir)) | {a.part})
        counts["split"] = a.split
    stages = prior_stages(run_dir) if a.plan else []
    fps = assemble.manifest_fingerprints(choices, ROOT / "data" / "raw")
    store.write_manifest(run_dir, a.name, choices["seeds"], conds, counts, fps,
                         ai="live", answers_fingerprint=answers_fingerprint(live_dir), level_source=levels)
    if a.plan:  # one record per stage is kept (the manifest itself is the latest state, as its readers expect)
        man = store.read_json(run_dir / "manifest.json")
        fps = dict(fps, code=filing.code_fp(), **{"extra:" + k: v for k, v in plan_extras(a).items()})
        man["stages"] = stages + [{"part": a.part, "rule": a.rule, "at": filing.now_local(), "counts": counts,
                                   "fingerprints": fps, "answers_fingerprint": man.get("answers_fingerprint")}]
        store.write_json(run_dir / "manifest.json", man)
    write_unusable(run_dir, st, choices, live_dir)
    # 3. the judge
    jcol, rows, srows, jobs, sample, vmap = find_judge_calls(run_dir, choices, answers, visit_tokens(live_dir, choices),
                                                             levels)
    store.write_jsonl(run_dir / "judge.jsonl", sorted(rows, key=lambda r: (r["visit_id"], r["item_id"], r["rule"])))
    if sample:
        store.write_jsonl(run_dir / "judge_sample.jsonl", srows)
        store.write_json(run_dir / "judge_agreement.json", judge.compare_with_readers(srows, sample, vmap, choices))
    # 4. the score, which calls no AI
    scores = score.score_run(run_dir, wiring, choices, a.filing_dir, levels)
    if a.plan:  # the parts that stand apart (hidden instruction, repeat check), from the scored rows; counts only
        apart = score_parts.score_parts(run_dir, scores, choices)
        store.write_json(run_dir / "scores_parts.json", apart)
        print(score_parts.counts_line(apart))
    lo = scores["left_out"]
    print("left out of every score: %d units (%d of them crashed)" % (
        lo["visits"], sum(n for k, n in lo["by_step_and_reason"].items() if k.endswith(": crashed"))))
    print("ran %d visits under %d conditions into %s" % (len(chosen), len(conds), run_dir))
    print("judge: %d texts for the advice rules, %d judged; marked sample %d, %d judged" % (
        len(jobs), len(rows), len(sample), len(srows)))
    if len(jcol):
        paths = export(live_dir, jcol.rows(), a.batch_size, choices)
        report_missing(jcol.rows(), paths, "judge", choices)
        return WAITING
    export(live_dir, [], 0, choices)
    print("nothing is missing; scores written to %s" % (run_dir / "scores.json"))
    print(score.render_header(scores["header"]))
    return 0


def cmd_export(a):
    """Only work out the missing chain calls and write them; the bench and the judge wait for `run`."""
    choices, wiring, rchoices, chosen, plan, conds, unplaced = setup(a)
    live_dir = Path(a.live_dir)
    legacy_check(live_dir, True)
    answers = ai_live.AnswerStore(live_dir).answers()
    todo = incomplete(Path(a.runs_dir) / a.name, chosen, conds) if a.plan else [(v, conds) for v in chosen]
    collector, stopped, crashed = find_chain_calls([v for v, _ in todo], plan, conds, choices, wiring, rchoices, answers,
                                                   ai_live.private_dir(live_dir) / "_scratch", visit_tokens(live_dir, choices))
    paths = export(live_dir, collector.rows(), a.batch_size, choices)
    if len(collector):
        report_missing(collector.rows(), paths, "chain", choices)
        return WAITING
    print("no chain call is missing; `run` will run the bench and work out the judge's calls")
    return 0


def cmd_import(a):
    choices = datasets.default_choices()
    watcher, reviewer, judge_id = prompt_ids(choices)
    live_dir = Path(a.live_dir)
    legacy_check(live_dir, False)
    chosen = select(visits.read_cases(a.visits, a.experiment), a.split)
    guard(a, choices, chosen[:a.limit] if a.limit else chosen)
    st = ai_live.AnswerStore(live_dir)
    pending = ai_live.read_pending(live_dir)
    idmap = ai_live.read_idmap(live_dir)
    step_ids = [choices["prompts"][n] for n in choices["live"]["export_sets"]["steps"]]
    classify = ai_live.make_step_classifier(choices)
    validators = {judge_id: judge.make_validator(choices), watcher: validate_flags_answer_lenient,
                  reviewer: validate_flags_answer_lenient}
    extras = {pid: (lambda o: split_flags_answer(o)[1]) for pid in (watcher, reviewer)}
    total = {"stored": 0, "already": 0, "refused": []}
    for f in a.files:
        rows = ai_live.read_answer_file(f)
        res = ai_live.import_answers(st, pending, rows, allow_empty=step_ids, validators=validators,
                                     classifiers={pid: classify for pid in step_ids}, idmap=idmap, extras=extras)
        print("%s: stored %d, already stored %d, refused %d" % (f, res["stored"], res["already"], len(res["refused"])))
        total["stored"] += res["stored"]
        total["already"] += res["already"]
        total["refused"] += [dict(r, file=str(f)) for r in res["refused"]]
    held = Counter(r["prompt_id"] for r in st.rows() if r.get("extra_lines"))  # 15 Nov audit: kept visible
    print("stored answers with extra lines (kept apart, never a flag), by prompt: %s" % (
        ", ".join("%s %d" % kv for kv in sorted(held.items())) or "none"))
    for r in total["refused"][:20]:
        print("  refused %s line %d: %s" % (r["file"], r["line"], r["reason"]))
    if len(total["refused"]) > 20:
        print("  and %d more" % (len(total["refused"]) - 20))
    return 1 if total["refused"] else 0


def cmd_status(a):
    legacy_check(a.live_dir, False)
    st = ai_live.AnswerStore(a.live_dir)
    pending = ai_live.read_pending(a.live_dir)
    print("stored answers: %d (%d marked unusable)" % (len(st.answers()), len(st.unusable())))
    print("pending calls: %d %s" % (len(pending), dict(Counter(c["prompt_id"] for c in pending.values()))))
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("command", choices=["run", "export", "import", "status"])
    ap.add_argument("files", nargs="*", help="answer files, for import")
    ap.add_argument("--experiment", type=int, choices=[1, 2], required=True,
                    help="1: transcripts (the words flow), 2: questions (the advice flow); the cases, the run folder and the live folder are separate")
    ap.add_argument("--split", choices=sorted(SPLITS), default="tune", help="tuning visits unless told otherwise")
    ap.add_argument("--name", default=None, help="run folder name under runs/ (default advice_<split>_e<experiment>)")
    ap.add_argument("--cases", "--visits", dest="visits", default=None,
                    help="the case file (default data/cases/exp<experiment>.jsonl)")
    ap.add_argument("--live-dir", default=None, help="default live_e<experiment>/")
    ap.add_argument("--trial", type=int, default=None, metavar="N",
                    help="N clean practice cases plus the practice violations of the experiment, each on a different practice case")
    ap.add_argument("--runs-dir", default=str(ROOT / "runs"))
    ap.add_argument("--limit", type=int, default=None, help="only the first n visits of the split")
    ap.add_argument("--conditions", default=None, help="comma list, for example A,B (default: A,A+,B; C is still available)")
    ap.add_argument("--ai-parts", choices=["on", "off"], default="on",
                    help="off: the review and the monitor run their program parts only (no AI call for them); the manifest records it")
    ap.add_argument("--batch-size", type=int, default=0, help="also write the missing calls in files of this many")
    ap.add_argument("--after-freeze-change", default=None, metavar="REASON",
                    help="go on although a prompt, the design choices or the scorer changed since the freeze; "
                         "the change and this reason are kept in live/frozen.json")
    ap.add_argument("--filing-dir", default=None, help=argparse.SUPPRESS)  # tests: another folder than the project's
    ap.add_argument("--levels", choices=["reader_first", "judge_all"], default=None,
                    help="where certainty levels come from: the program's word reader first (default, D: rules.level_source) "
                         "or the judge for every advice text; the run's manifest records the choice")
    ap.add_argument("--sealed", action="store_true", help="add the sealed faults after the development ones")
    ap.add_argument("--plan", default=None, metavar="PLAN.json",
                    help="run the units of a plan made by tools/make_plan.py (with --part); a unit is one case with at most one planted violation")
    ap.add_argument("--part", choices=list(units.PARTS), default=None,
                    help="with --plan: the part of the plan to run (clean, planted, kept_copy, hidden, repeat)")
    ap.add_argument("--rule", type=int, choices=[1, 2, 3, 4, 5, 6], default=None,
                    help="with --plan: only the rows of this rule (clean: the clean twins of that rule's planted units)")
    ap.add_argument("--catalogue", default=None, metavar="FILE",
                    help="with --plan, Experiment 1: the list of variants (default: exp1_catalogue.json beside the plan)")
    ap.add_argument("--faults", default=None, metavar="FILE",
                    help="with --plan, Experiment 2: the faults file of tools/make_plan.py faults-exp2 (parts planted and repeat)")
    a = ap.parse_args(argv)
    a.name = a.name or ("advice_%s_e%d" % ("trial" if a.trial else a.split, a.experiment))
    a.visits = a.visits or str(visits.case_path(a.experiment))
    a.live_dir = a.live_dir or str(ROOT / ("live_e%d" % a.experiment))
    try:
        return {"run": cmd_run, "export": cmd_export, "import": cmd_import, "status": cmd_status}[a.command](a)
    except CustodyError as e:
        print("error: %s" % e)
        return 2


if __name__ == "__main__":
    sys.exit(main())
