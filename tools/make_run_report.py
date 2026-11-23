#!/usr/bin/env python3
"""Run report page: one self-contained HTML page that shows, case by case, what happened in a run.

    python3 tools/make_run_report.py <run folder> [<run folder> ...] --out <file.html>

Written for a reader who is not a programmer. Reads only files that the run folder holds (manifest.json,
visits.jsonl, results.jsonl, texts.jsonl, signals.jsonl, own_log.jsonl, ai_calls.jsonl, journal/, receipts/,
hidden/plan.jsonl, hidden/truth.jsonl, scores.json or scores.partial.json, judge.jsonl, unusable_visits.json,
refusal_candidates.json). Every file is optional: a missing or odd field is skipped, never a crash.
Standard library only. Makes no network call and no model call. Writes only the --out file.

The expert grade of a case is never printed next to a text; it is not read at all.
"""
import argparse
import datetime
import html
import json
import sys
from collections import Counter, OrderedDict, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

CUT = 1200  # characters of a text shown before "show all"

# The words of the test plan ("The words we use"): one name for each method.
METHODS = OrderedDict([("A", "Promised"), ("A+", "Monitored"), ("B", "Checked")])
METHOD_CLASS = {"A": "mp", "A+": "mm", "B": "mc"}
METHOD_SAYS = {
    "A": "the vendor promises, the AI steps are told the rules, a review reads the log and the texts after the case",
    "A+": "Promised plus a monitor that reads every message between two steps and can flag but not stop",
    "B": "a label on every piece of content and a checker program that every handover must pass; it can stop a handover",
}
# Who raises a signal (the signal's "by").
BY_WORDS = {"review": "the review", "watcher": "the monitor", "gate": "the checker",
            "ledger": "the receipt check", "proof": "the proof"}
# What each method counts as its own (config conditions.<name>.signals_counted); used when the config is not found.
COUNTED_DEFAULT = {"A": ["review"], "A+": ["review", "watcher"], "B": ["gate", "ledger"]}

RULE_WORDS = {
    1: "Your words went only to named places.",
    2: "Every copy of your words has a recorded deletion before its deadline.",
    3: "Every handover was recorded first, and an outside witness holds the fingerprint of each record.",
    4: "Every claim in your advice names its source.",
    5: "The certainty stated in your advice matches the experts' grade.",
    6: "The part written by AI is marked.",
}
EXPERIMENT_RULES = {1: [1, 2, 3], 2: [4, 5, 6]}
EXPERIMENT_NAMES = {1: "Experiment 1: words going out (rules 1 to 3)", 2: "Experiment 2: advice coming in (rules 4 to 6)"}
FLOW_ORDER = ["audio", "transcript", "note_draft", "note", "question", "answer", "plan", "patient_note"]
KIND_WORDS = {
    "audio": "recording", "transcript": "transcript", "note_draft": "note draft", "note": "note in the chart",
    "question": "question", "answer": "evidence tool's answer", "plan": "plan",
    "patient_note": "note for the patient",
}
OUTCOME_WORDS = {"blocked": "blocked", "flagged": "flagged", "silent": "missed", "missed": "missed",
                 "did_not_fire": "did not take effect", "unjudged": "not yet judged"}

STAND_IN_BAND = "stand-in text: these numbers measure nothing"


# ------------------------------------------------------------------------------------------ reading files

def read_jsonl(path):
    out = []
    try:
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    out.append(json.loads(line))
                except ValueError:
                    continue
    except (OSError, UnicodeDecodeError):
        return []
    return [r for r in out if isinstance(r, dict)]


def read_json(path, default=None):
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError, UnicodeDecodeError):
        return default


def g(d, *keys, default=None):
    """d[k1][k2]... with every step safe."""
    cur = d
    for k in keys:
        if isinstance(cur, dict) and k in cur:
            cur = cur[k]
        else:
            return default
    return cur


def esc(x):
    return html.escape("" if x is None else str(x), quote=True)


def load_config():
    cfg = read_json(ROOT / "config" / "design_choices.json", {}) or {}
    counted = dict(COUNTED_DEFAULT)
    conds = cfg.get("conditions") if isinstance(cfg, dict) else None
    if isinstance(conds, dict):
        for k in METHODS:
            sc = g(conds, k, "signals_counted")
            if isinstance(sc, list):
                counted[k] = [str(s) for s in sc]
    wiring = read_json(ROOT / "wiring" / "wiring.json", {}) or {}
    steps = {}
    for s in g(wiring, "plumbing", "steps", default=[]) or []:
        if isinstance(s, dict) and s.get("id"):
            steps[s["id"]] = bool(s.get("ai"))
    places = {}
    pl = g(wiring, "promise", "places")
    if isinstance(pl, dict):
        for k, v in pl.items():
            if isinstance(v, dict):
                places[k] = v.get("who") or ""
    elif isinstance(pl, list):
        for v in pl:
            if isinstance(v, dict) and v.get("place"):
                places[v["place"]] = v.get("who") or ""
    return {"counted": counted, "steps": steps, "places": places}


class Run:
    """Everything one run folder holds, read defensively."""

    def __init__(self, folder, cfg):
        self.dir = Path(folder)
        self.cfg = cfg
        d = self.dir
        self.name = d.name
        self.manifest = read_json(d / "manifest.json", {}) or {}
        self.visits = {r.get("visit_id"): r for r in read_jsonl(d / "visits.jsonl") if r.get("visit_id")}
        self.results = read_jsonl(d / "results.jsonl")
        self.texts = read_jsonl(d / "texts.jsonl")
        self.signals = read_jsonl(d / "signals.jsonl")
        self.own_log = read_jsonl(d / "own_log.jsonl")
        self.ai_calls = read_jsonl(d / "ai_calls.jsonl")
        self.plan_rows = read_jsonl(d / "hidden" / "plan.jsonl")
        self.truth = read_jsonl(d / "hidden" / "truth.jsonl")
        self.judge = read_jsonl(d / "judge.jsonl")
        self.unusable = read_json(d / "unusable_visits.json", None)
        self.candidates = read_json(d / "refusal_candidates.json", None)
        self.scores, self.scores_file = None, None
        for fn in ("scores.json", "scores.partial.json"):
            s = read_json(d / fn, None)
            if isinstance(s, dict):
                self.scores, self.scores_file = s, fn
                break
        self.partial = self.scores_file == "scores.partial.json" or (
            self.scores is not None and g(self.scores, "header", "complete") is False)
        self.experiment = self._experiment()
        self.plan = {r.get("visit_id"): r.get("fault") for r in self.plan_rows}
        self.case_ids = self._case_ids()
        self.run_of = {}  # (visit_id, condition) -> run_id of rep 0
        for r in self.results:
            if r.get("rep", 0) in (0, None) and r.get("visit_id") and r.get("condition"):
                self.run_of.setdefault((r["visit_id"], r["condition"]), r.get("run_id"))
        self.signals_by_run = defaultdict(list)
        for s in self.signals:
            self.signals_by_run[s.get("run_id")].append(s)
        self.truth_by_run = defaultdict(list)
        for e in self.truth:
            self.truth_by_run[e.get("run_id")].append(e)
        self.log_by_run = defaultdict(list)
        for e in self.own_log:
            self.log_by_run[e.get("run_id")].append(e)
        self.texts_of = defaultdict(OrderedDict)  # visit -> item_id -> {row, conditions}
        self._group_texts()
        self.attempts = []
        if self.scores and isinstance(self.scores.get("attempts"), list):
            self.attempts = [a for a in self.scores["attempts"] if isinstance(a, dict)]

    def _experiment(self):
        e = g(self.manifest, "counts", "experiment")
        if e in (1, 2):
            return e
        for r in self.results:
            if r.get("experiment") in (1, 2):
                return r["experiment"]
        for v in self.visits.values():
            try:
                if int(v.get("experiment")) in (1, 2):
                    return int(v.get("experiment"))
            except (TypeError, ValueError):
                pass
        if self.name.endswith("_e1"):
            return 1
        if self.name.endswith("_e2"):
            return 2
        kinds = {t.get("item", {}).get("kind") for t in self.texts}
        return 1 if "transcript" in kinds else 2

    def _case_ids(self):
        ids = []
        for src in (self.plan_rows, self.results, list(self.visits.values())):
            for r in src:
                v = r.get("visit_id")
                if v and v not in ids:
                    ids.append(v)
            if ids:
                break
        for r in self.results:
            v = r.get("visit_id")
            if v and v not in ids:
                ids.append(v)
        return ids

    def _group_texts(self):
        want = set(METHODS)
        run_cond = {}
        for r in self.results:
            run_cond[r.get("run_id")] = r.get("condition")
        for t in self.texts:
            it = t.get("item") or {}
            vid = it.get("visit_id")
            iid = it.get("item_id")
            if not vid or not iid:
                continue
            cond = run_cond.get(t.get("run_id"))
            if cond is None:
                parts = str(t.get("run_id", "")).split(".")
                cond = parts[1] if len(parts) > 1 else None
            if cond not in want:
                continue
            slot = self.texts_of[vid].setdefault(iid, {"row": t, "conditions": []})
            if cond not in slot["conditions"]:
                slot["conditions"].append(cond)

    # ------------------------------------------------------------------ small answers
    def planted(self, vid):
        f = self.plan.get(vid)
        return f if isinstance(f, dict) else None

    def rules(self):
        base = list(EXPERIMENT_RULES.get(self.experiment, []))
        for a in self.attempts:
            r = a.get("rule")
            if isinstance(r, int) and r not in base:
                base.append(r)
        return sorted(base)

    def is_stand_in(self):
        ai = self.manifest.get("ai")
        if ai == "canned":
            return True
        if g(self.scores or {}, "header", "stand_in_text"):
            return True
        return False

    def ai_kind(self):
        ai = self.manifest.get("ai")
        if ai == "canned":
            return "stand-in text (no real AI wrote these texts)"
        if ai == "live":
            return "real AI"
        if ai is None:
            return "not stated in the manifest"
        return str(ai)

    def counted(self, cond):
        return self.cfg["counted"].get(cond, [])

    def counting_signals(self, vid, cond, rule=None):
        run = self.run_of.get((vid, cond))
        out = []
        for s in self.signals_by_run.get(run, []):
            if s.get("by") in self.counted(cond) and isinstance(s.get("rule"), int) and 1 <= s["rule"] <= 6:
                if rule is None or s["rule"] == rule:
                    out.append(s)
        return sorted(out, key=lambda s: (s.get("t") is None, s.get("t") or 0))


# ------------------------------------------------------------------------------------------ wording

def signal_who(s):
    by = BY_WORDS.get(s.get("by"), str(s.get("by") or "someone"))
    part = s.get("part")
    if s.get("by") == "review" and part in ("program", "ai"):
        return "the review's %s" % ("program" if part == "program" else "AI")
    if s.get("by") == "watcher" and part in ("program", "ai"):
        return "the monitor's %s" % ("program" if part == "program" else "AI")
    if s.get("by") == "gate":
        return "the checker's program"
    return by


def signal_short(s):
    who = signal_who(s)
    if s.get("level") == "block":
        return "stopped by %s" % who
    return "flag from %s" % who


def phrase_for(run, vid, cond, rows, planted):
    """Three or four words for what a method did with a case."""
    if planted:
        if rows:
            bits = []
            multi = len({r.get("rule") for r in rows}) > 1
            for r in rows:
                out = r.get("outcome")
                sigs = run.counting_signals(vid, cond, r.get("rule"))
                if out == "blocked":
                    gate = [s for s in sigs if s.get("level") == "block"]
                    txt = "stopped at the handover" if gate else "rule held in this run"
                elif out == "flagged":
                    txt = ("flag from %s" % signal_who(sigs[0])) if sigs else "flagged"
                elif out in ("silent", "missed"):
                    txt = "nothing raised"
                elif out == "unjudged":
                    txt = "not yet judged"
                elif out == "did_not_fire":
                    txt = "plant did not take effect"
                else:
                    txt = str(out)
                bits.append(("rule %s: " % r.get("rule") if multi else "") + txt)
            return "; ".join(bits)
        sigs = run.counting_signals(vid, cond, (planted.get("rule") if isinstance(planted.get("rule"), int) else None))
        if not sigs:
            return "nothing raised"
        s = sigs[0]
        return signal_short(s)
    sigs = run.counting_signals(vid, cond)
    if not sigs:
        return "nothing raised"
    return "false alarm: " + signal_short(sigs[0])


def fault_kind_words(planted):
    if not planted:
        return None
    says = planted.get("says") or planted.get("fault_id") or "a planted violation"
    return says


# ------------------------------------------------------------------------------------------ summary tables

def counts_from_attempts(run):
    """{rule: {cond: Counter(blocked, flagged, silent, did_not_fire)}} from the scorer's attempt rows."""
    out = defaultdict(lambda: defaultdict(Counter))
    for a in run.attempts:
        r, c, o = a.get("rule"), a.get("condition"), a.get("outcome")
        if isinstance(r, int) and c in METHODS:
            out[r][c]["silent" if o == "missed" else o] += 1
    return out


def cell_of(scores, table, rule, cond):
    v = g(scores or {}, table, str(rule), cond)
    return v if isinstance(v, dict) else None


def num(x, nd=2):
    if x is None:
        return "-"
    try:
        f = float(x)
    except (TypeError, ValueError):
        return esc(x)
    return ("%d" % f) if abs(f - round(f)) < 1e-9 else ("%.*f" % (nd, f))


def _active(table):
    """True when any cell of an in_words table holds a count."""
    if not isinstance(table, dict):
        return False
    for rv in table.values():
        if isinstance(rv, dict):
            for cell in rv.values():
                if isinstance(cell, dict) and (cell.get("violations") or cell.get("clean_units")):
                    return True
    return False


def _flat(d, path=()):
    """Leaf dicts (or scalars) of a nested dict, with the path of keys that leads to each."""
    if isinstance(d, dict) and d and any(isinstance(v, dict) for v in d.values()):
        for k, v in d.items():
            yield from _flat(v, path + (k,))
    elif d not in ({}, [], None):
        yield path, d


def _label(k):
    k = str(k)
    return "Rule %s" % k if k in ("1", "2", "3", "4", "5", "6") else k.replace("_", " ")


def _vals(v):
    if isinstance(v, dict):
        return "; ".join("%s: %s" % (str(a).replace("_", " "), _vals(b) if isinstance(b, dict) else num(b) if isinstance(b, (int, float)) else b)
                         for a, b in v.items())
    return num(v) if isinstance(v, (int, float)) else str(v)


def dict_table(title, data, note=None, fold=True):
    """A small table of any nested dict: one row per leaf, the path on the left, the values on the right."""
    if data in (None, {}, [], "") or (isinstance(data, dict) and not any(True for _ in _flat(data))):
        return ""
    if isinstance(data, (int, float, str)):
        body = "<p>%s</p>" % esc(data)
    elif isinstance(data, dict):
        rows = []
        for path, leaf in _flat(data):
            rows.append("<tr><td>%s</td><td>%s</td></tr>" % (esc(" / ".join(_label(x) for x in path) or "-"), esc(_vals(leaf))))
        body = '<table class="grid small"><thead><tr><th>Where</th><th>What the scorer reports</th></tr></thead><tbody>%s</tbody></table>' % "".join(rows)
    else:
        body = "<p>%s</p>" % esc(json.dumps(data))
    if note:
        body += '<p class="note">%s</p>' % esc(note)
    return '<details class="fold"%s><summary>%s</summary>%s</details>' % ("" if fold else " open", esc(title), body)


GRADE_WORDS = {"pass": "pass", "fail": "fail", "inconclusive": "inconclusive"}


def in_words_cell(c, c_class):
    if not isinstance(c, dict):
        return '<td class="%s">-</td>' % c_class
    parts = []
    if c.get("grade") is not None:
        parts.append('<span class="grade">%s</span>' % esc(c.get("grade")))
    parts.append('<span class="n">blocked <b>%s</b></span><span class="n">flagged <b>%s</b></span>'
                 '<span class="n miss">missed <b>%s</b></span><span class="tot">of %s planted</span>' % (
                     num(c.get("blocked")), num(c.get("flagged")), num(c.get("missed")), num(c.get("violations"))))
    if c.get("upper") is not None:
        parts.append('<span class="tot">the share missed could be as high as %s</span>' % num(c.get("upper"), 3))
    parts.append('<span class="fa">false alarms <b>%s</b> on %s clean</span>' % (num(c.get("false_alarms")), num(c.get("clean_units"))))
    if c.get("unjudged"):
        parts.append('<span class="fa">%s text(s) not yet read by the judge</span>' % num(c.get("unjudged")))
    if c.get("decided_by"):
        parts.append('<span class="tech">decided by: %s</span>' % esc(c.get("decided_by")))
    return '<td class="%s">%s</td>' % (c_class, "".join(parts))


def in_words_summary(run):
    iw = run.scores.get("in_words")
    main = iw.get("table")
    practice = g(iw, "practice_set", "table")
    use, sentence, grades = main, "", None
    if not _active(main) and _active(practice):
        use, grades = practice, g(iw, "practice_set", "grades")
        sentence = ("The main table is empty because every case in this run is a practice case; the table below is the "
                    "practice table, and practice results are never counted.")
    names = iw.get("methods") if isinstance(iw.get("methods"), list) and len(iw["methods"]) == 3 else list(METHODS.values())
    cond_of = dict(zip(names, METHODS))  # name -> condition letter
    rules = sorted({int(k) for k in (use or {}) if str(k).isdigit()} | set(run.rules()))
    h = []
    if sentence:
        h.append('<p class="note"><b>%s</b></p>' % esc(sentence))
    h.append('<table class="grid"><thead><tr><th>Rule</th>')
    for n, c in zip(names, METHODS):
        h.append('<th class="%s">%s</th>' % (METHOD_CLASS[c], esc(n)))
    h.append("<th>The least that is enough</th></tr></thead><tbody>")
    for r in rules:
        rv = (use or {}).get(str(r)) or {}
        h.append('<tr><th class="rule">Rule %d<span>%s</span></th>' % (r, esc(RULE_WORDS.get(r, ""))))
        for n, c in zip(names, METHODS):
            cell = rv.get(n) if isinstance(rv.get(n), dict) else rv.get(c)
            if grades and isinstance(cell, dict) and cell.get("grade") is None:
                cell = dict(cell, grade=g(grades, str(r), n))
            h.append(in_words_cell(cell, METHOD_CLASS[c]))
        h.append("<td>%s</td></tr>" % esc(rv.get("least_enough", "-") if rv.get("least_enough") is not None else "-"))
    h.append("</tbody></table>")
    notes = []
    if run.partial:
        notes.append("<b>These scores are partial.</b> The scorer wrote %s: the judge has not yet read every advice text, "
                     "so the cells that depend on it are not final." % esc(run.scores_file or "a partial scores file"))
    notes.append("Blocked: the method stopped the violation. Flagged: it happened and the method raised a flag for it. "
                 "Missed: it happened and the method raised nothing for it. A false alarm is a flag on a clean case. "
                 "Numbers are the scorer's own (in_words).")
    h.append('<p class="note">%s</p>' % " ".join(notes))
    extras = [
        ("By kind of violation", iw.get("by_kind")), ("Flags by part (program or AI)", iw.get("flags_by_part")),
        ("False alarms", iw.get("false_alarms")), ("The judge read the entering answer differently from the grade it was written from", iw.get("entry_errors")),
        ("Natural violations (an AI step broke a rule by itself)", iw.get("natural_violations")),
        ("Parts reported apart", iw.get("parts_reported_apart")), ("Cases left out", iw.get("cases_left_out")),
        ("The reader's program against the judge", iw.get("reader_versus_judge")),
        ("Rows with no clean run of the same case to compare with", iw.get("unpaired_rows")),
    ]
    for title, data in extras:
        if title.startswith("Rows") and isinstance(data, (int, float)):
            h.append('<p class="note">%s: <b>%s</b></p>' % (esc(title), num(data)))
            continue
        h.append(dict_table(title, data))
    ps = iw.get("practice_set")
    if isinstance(ps, dict):
        rest = {k: v for k, v in ps.items() if k != "label"}
        pt = {}
        for r, rv in (rest.get("table") or {}).items():
            if isinstance(rv, dict):
                pt[r] = {METHODS.get(k, k): {a: b for a, b in v.items() if a in ("violations", "blocked", "flagged", "missed", "false_alarms", "clean_units", "grade", "unpaired")}
                         for k, v in rv.items() if isinstance(v, dict)}
        h.append('<h4>%s</h4>' % esc("Practice set: never counted"))
        h.append(dict_table("Practice cases, by rule and method", pt, "Practice cases are used to check the machinery. Their results are not part of the main table.", fold=True))
    return "".join(h)


def summary_html(run):
    if run.scores and isinstance(run.scores.get("in_words"), dict) and isinstance(run.scores["in_words"].get("table"), dict):
        try:
            return in_words_summary(run)
        except Exception:  # noqa: BLE001  fall back to the older reading of the scores
            pass
    return summary_old_html(run)


def summary_old_html(run):
    sc = run.scores
    rules = run.rules()
    if sc is None:
        return ('<p class="note">No scores file (scores.json or scores.partial.json) is in this run folder, so there is '
                'no summary table. The case tables below are built from the signals the run itself holds.</p>')
    counts = counts_from_attempts(run)
    have_attempts = bool(run.attempts)
    h = ['<table class="grid"><thead><tr><th>Rule</th>']
    for c, name in METHODS.items():
        h.append('<th class="%s">%s</th>' % (METHOD_CLASS[c], esc(name)))
    h.append("</tr></thead><tbody>")
    for r in rules:
        h.append('<tr><th class="rule">Rule %d<span>%s</span></th>' % (r, esc(RULE_WORDS.get(r, ""))))
        for c in METHODS:
            cnt = counts.get(r, {}).get(c, Counter())
            cell = cell_of(sc, "table", r, c)
            tune = cell_of(sc, "tune_table", r, c)
            fa_cell, fa_note = cell, ""
            if (not fa_cell or not fa_cell.get("clean_units")) and tune and tune.get("clean_units"):
                fa_cell, fa_note = tune, " (practice cases)"
            if have_attempts:
                parts = ['<span class="n">blocked <b>%d</b></span>' % cnt.get("blocked", 0),
                         '<span class="n">flagged <b>%d</b></span>' % cnt.get("flagged", 0),
                         '<span class="n miss">missed <b>%d</b></span>' % cnt.get("silent", 0)]
                if cnt.get("did_not_fire"):
                    parts.append('<span class="n">did not take effect <b>%d</b></span>' % cnt["did_not_fire"])
                total = sum(cnt.values())
                parts.append('<span class="tot">of %d planted</span>' % total)
            else:
                parts = ['<span class="tot">no list of attempts in the scores</span>']
                if cell and cell.get("attempts") is not None:
                    parts.append('<span class="n miss">missed <b>%s</b></span> of %s planted' % (
                        num(cell.get("silent")), num(cell.get("attempts"))))
            if fa_cell and fa_cell.get("clean_units") is not None:
                parts.append('<span class="fa">false alarms <b>%s</b> on %s clean%s</span>' % (
                    num(fa_cell.get("false_alarms")), num(fa_cell.get("clean_units")), fa_note))
            else:
                parts.append('<span class="fa">false alarms: not given</span>')
            h.append('<td class="%s">%s</td>' % (METHOD_CLASS[c], "".join(parts)))
        h.append("</tr>")
    h.append("</tbody></table>")
    notes = []
    if run.partial:
        notes.append("<b>These scores are partial.</b> The scorer wrote %s: the judge has not yet read every advice text "
                     "that the program cannot read, so the cells for the rules it covers rest on the program's reading "
                     "only and carry no call." % esc(run.scores_file or "a partial scores file"))
    notes.append("Counts come from the scorer's list of attempts (one row per run, rule and method, over every split "
                 "the file lists); false alarms come from the scorer's tables. The three methods are the code's "
                 "conditions A, A+ and B.")
    if any(k == "C" for (_, k) in run.run_of):
        notes.append("The folder also holds a fourth condition, C (Checked with a proof). It is not a column here.")
    h.append('<p class="note">%s</p>' % " ".join(notes))
    # the scorer's own tables
    for key, title in (("table", "The scorer's own table"), ("tune_table", "The scorer's table for practice cases only")):
        if not isinstance(sc.get(key), dict):
            continue
        h.append('<details class="fold"><summary>%s</summary>' % esc(title))
        h.append('<table class="grid small"><thead><tr><th>Rule</th>')
        for c, name in METHODS.items():
            h.append('<th class="%s">%s</th>' % (METHOD_CLASS[c], esc(name)))
        h.append("</tr></thead><tbody>")
        for r in rules:
            h.append("<tr><th>Rule %d</th>" % r)
            for c in METHODS:
                cell = cell_of(sc, key, r, c)
                if not cell:
                    h.append("<td>-</td>")
                    continue
                h.append("<td>missed %s of %s planted; false alarms %s of %s clean; call: %s</td>" % (
                    num(cell.get("silent")), num(cell.get("attempts")), num(cell.get("false_alarms")),
                    num(cell.get("clean_units")), esc(cell.get("call", "-"))))
            h.append("</tr>")
        h.append("</tbody></table></details>")
    return "".join(h)


# ------------------------------------------------------------------------------------------ case table

def case_table_html(run):
    h = ['<table class="grid cases"><thead><tr><th>Case</th><th>Clean, or what was planted</th>']
    for c, name in METHODS.items():
        h.append('<th class="%s">%s</th>' % (METHOD_CLASS[c], esc(name)))
    h.append("</tr></thead><tbody>")
    for vid in run.case_ids:
        planted = run.planted(vid)
        kind = ('<span class="plant">planted</span> %s <span class="tech">(%s, rule %s)</span>' % (
            esc(fault_kind_words(planted)), esc(planted.get("fault_id")), esc(planted.get("rule")))
            if planted else "clean")
        h.append('<tr><td><a href="#%s">%s</a></td><td>%s</td>' % (anchor(run, vid), esc(vid), kind))
        for c in METHODS:
            if (vid, c) not in run.run_of:
                h.append('<td class="%s">not run</td>' % METHOD_CLASS[c])
                continue
            rows = [a for a in run.attempts if a.get("visit_id") == vid and a.get("condition") == c]
            h.append('<td class="%s">%s</td>' % (METHOD_CLASS[c], esc(phrase_for(run, vid, c, rows, planted))))
        h.append("</tr>")
    h.append("</tbody></table>")
    return "".join(h)


def anchor(run, vid):
    return "case-%s-%s" % (esc(run.name).replace(" ", "_"), esc(vid))


# ------------------------------------------------------------------------------------------ one case

def text_block(text):
    text = text or ""
    if len(text) <= CUT:
        return '<pre class="txt">%s</pre>' % esc(text)
    return ('<pre class="txt">%s&hellip;</pre><details class="more"><summary>show all (%d characters)</summary>'
            '<pre class="txt">%s</pre></details>' % (esc(text[:CUT]), len(text), esc(text)))


def who_made(run, vid, it):
    mb = it.get("made_by")
    if mb == "intake":
        return "a program (put in at the start of the case)"
    ai = run.cfg["steps"].get(mb)
    if ai:
        return "an AI (stand-in text)" if run.manifest.get("ai") == "canned" else "an AI"
    if ai is False:
        return "a program"
    return "unknown"


def texts_html(run, vid):
    slots = list(run.texts_of.get(vid, {}).values())
    if not slots:
        return '<p class="note">No texts for this case in texts.jsonl.</p>'

    def key(s):
        it = s["row"].get("item") or {}
        k = it.get("kind")
        return (FLOW_ORDER.index(k) if k in FLOW_ORDER else 99, s["row"].get("t") or 0)
    h = []
    for s in sorted(slots, key=key):
        row = s["row"]
        it = row.get("item") or {}
        place = row.get("place")
        who = run.cfg["places"].get(place)
        under = ", ".join(METHODS[c] for c in METHODS if c in s["conditions"])
        diff = ""
        if len(s["conditions"]) < len([c for c in METHODS if (vid, c) in run.run_of]):
            diff = ' <span class="diff">this exact text exists only under: %s</span>' % esc(under)
        h.append('<div class="text"><div class="th"><b>%s</b> &middot; at %s%s &middot; made by %s &middot; tick %s%s</div>%s</div>' % (
            esc(KIND_WORDS.get(it.get("kind"), it.get("kind"))), esc(place),
            (" (%s)" % esc(who)) if who else "", esc(who_made(run, vid, it)), esc(row.get("t")), diff,
            text_block(it.get("text"))))
    return "".join(h)


def planted_html(run, vid):
    f = run.planted(vid)
    if not f:
        return '<p>Nothing was planted in this case.</p>'
    h = ['<p><span class="plant">planted</span> <b>%s</b> (%s, rule %s, kind %s)</p>' % (
        esc(f.get("says")), esc(f.get("fault_id")), esc(f.get("rule")), esc(f.get("kind")))]
    tech = []
    for op in f.get("ops") or []:
        if isinstance(op, dict):
            tech.append("step change: %s" % ", ".join("%s=%s" % (k, v) for k, v in op.items()))
    for p in f.get("patch") or []:
        if isinstance(p, dict):
            tech.append("wiring change: %s %s" % (p.get("op"), p.get("path")))
    for ev in f.get("events") or []:
        if isinstance(ev, dict):
            tech.append("rare event: %s at handover %s" % (ev.get("on"), ev.get("at")))
    if tech:
        h.append('<p class="tech">%s</p>' % "<br>".join(esc(t) for t in tech))
    # where and when, from the true record of the Promised run (any run when that one is missing)
    run_id = None
    for c in METHODS:
        if (vid, c) in run.run_of:
            run_id = run.run_of[(vid, c)]
            break
    evs = [e for e in run.truth_by_run.get(run_id, []) if e.get("fault_id") or e.get("kind") in ("edited", "kept")]
    if evs:
        h.append('<table class="grid small"><thead><tr><th>Moment (tick)</th><th>What the true record shows</th>'
                 '<th>Where</th></tr></thead><tbody>')
        for e in sorted(evs, key=lambda e: (e.get("seq") is None, e.get("seq") or 0)):
            det = e.get("detail")
            h.append("<tr><td>%s</td><td>%s</td><td>%s</td></tr>" % (
                esc(e.get("t")), esc("%s%s" % (e.get("kind"), (": " + json.dumps(det, sort_keys=True)) if det else "")),
                esc(" to ".join(x for x in (e.get("place"), e.get("to_place")) if x) or "-")))
        h.append("</tbody></table>")
        h.append('<p class="note">From the true record of the %s run (%s). The same plant is made in every method\'s run.</p>'
                 % (esc(METHODS.get(next((c for c in METHODS if (vid, c) in run.run_of), "A"))), esc(run_id)))
    else:
        h.append('<p class="note">The true record holds no event marked with this plant.</p>')
    return "".join(h)


def describe_h(action, kind, frm, to):
    kind_w = KIND_WORDS.get(kind, kind or "?")
    if action == "delete":
        return "delete %s at %s" % (kind_w, frm)
    return "send %s %s to %s" % (kind_w, "from %s" % frm if frm else "", to)


def handover_rows(run, vid, cond):
    """[(hid, truth dict or None, record dict or None)] for one method's run."""
    run_id = run.run_of.get((vid, cond))
    truth = {}
    for e in run.truth_by_run.get(run_id, []):
        hid = e.get("handover_id")
        if not hid or e.get("kind") not in ("asked", "moved"):
            continue
        slot = truth.setdefault(hid, {"asked": None, "moved": None})
        slot[e["kind"]] = e
    record = OrderedDict()
    if cond == "B":
        j = read_jsonl(run.dir / "journal" / ("%s.jsonl" % run_id)) if run_id else []
        for r in j:
            ho = r.get("handover")
            if isinstance(ho, dict) and ho.get("handover_id"):
                record[ho["handover_id"]] = {"action": ho.get("action"), "from": ho.get("from_place"),
                                             "to": ho.get("to_place"), "kind": ho.get("kind"), "t": ho.get("t"),
                                             "decision": r.get("decision")}
            elif r.get("decision") == "close" or not isinstance(ho, dict):
                record["close#%s" % r.get("seq")] = {"action": "close", "from": None, "to": None, "kind": None,
                                                    "t": r.get("t"), "decision": r.get("decision")}
    else:
        for r in run.log_by_run.get(run_id, []):
            if r.get("action") in ("send", "delete") and r.get("handover_id"):
                record[r["handover_id"]] = {"action": r.get("action"), "from": r.get("from"), "to": r.get("to"),
                                            "kind": r.get("kind"), "t": r.get("t"), "decision": None}

    def order(hid):
        try:
            return (0, int(str(hid).rsplit("#", 1)[1]))
        except (IndexError, ValueError):
            return (1, str(hid))
    ids = sorted(set(truth) | {h for h in record if not h.startswith("close#")}, key=order)
    rows = [(hid, truth.get(hid), record.get(hid)) for hid in ids]
    return rows, [r for k, r in record.items() if k.startswith("close#")], run_id


def handover_html(run, vid, cond):
    rows, closes, run_id = handover_rows(run, vid, cond)
    if not run_id:
        return '<p class="note">Not run.</p>'
    what = {"A": "the system's log", "A+": "the system's log", "B": "the checker's record"}[cond]
    h = ['<table class="grid small"><thead><tr><th>#</th><th>What really moved (true record)</th>'
         "<th>What %s shows</th><th>Difference</th></tr></thead><tbody>" % esc(what)]
    nd = 0
    kept = [e for e in run.truth_by_run.get(run_id, []) if e.get("kind") == "kept"]
    for hid, tr, rec in rows:
        asked = (tr or {}).get("asked")
        moved = (tr or {}).get("moved")
        base = moved or asked
        if base:
            d = base.get("detail") or {}
            tcell = esc("%s (tick %s)" % (describe_h(d.get("action"), d.get("kind"), base.get("place"), base.get("to_place")), base.get("t")))
            tcell += "" if moved else " <i>asked, did not move</i>"
        else:
            tcell = "<i>nothing</i>"
        if rec:
            rcell = esc("%s (tick %s)" % (describe_h(rec.get("action"), rec.get("kind"), rec.get("from"), rec.get("to")), rec.get("t")))
            if rec.get("decision"):
                rcell += " <b>%s</b>" % esc(rec["decision"])
        else:
            rcell = "<i>no line</i>"
        diff = ""
        if moved and not rec:
            diff = "moved, but the record has no line for it"
        elif rec and not base:
            diff = "a line for something that was never asked for"
        elif rec and base:
            d = base.get("detail") or {}
            if (rec.get("action"), rec.get("from"), rec.get("to"), rec.get("kind")) != (
                    d.get("action"), base.get("place"), base.get("to_place"), d.get("kind")):
                diff = "the record names a different handover than the one that took place"
            elif rec.get("action") != "close" and not moved and cond != "B":
                diff = "the log shows a handover that did not take place"
        if diff:
            nd += 1
        h.append("<tr%s><td>%s</td><td>%s</td><td>%s</td><td>%s</td></tr>" % (
            ' class="differs"' if diff else "", esc(str(hid).rsplit("#", 1)[-1]),
            tcell, rcell,
            ('<b class="plant">%s</b>' % esc(diff)) if diff else ""))
    for e in kept:
        nd += 1
        d = e.get("detail") or {}
        h.append('<tr class="differs"><td>-</td><td>a copy of %s was kept at %s</td><td><i>no line</i></td>'
                 '<td><b class="plant">a copy exists that no record shows</b></td></tr>' % (
                     esc(KIND_WORDS.get(d.get("kind"), d.get("kind"))), esc(e.get("place"))))
    h.append("</tbody></table>")
    h.append('<p class="note">%s</p>' % (
        ("%d difference%s between the record and what really moved." % (nd, "" if nd == 1 else "s")) if nd
        else "The record and what really moved agree."))
    return "".join(h)


def signals_html(run, vid, cond):
    run_id = run.run_of.get((vid, cond))
    sigs = sorted(run.signals_by_run.get(run_id, []), key=lambda s: (s.get("t") is None, s.get("t") or 0))
    if not run_id:
        return '<p class="note">Not run.</p>'
    if not sigs:
        return '<p class="note">Nothing raised by anyone in this run.</p>'
    counted = run.counted(cond)
    h = ['<table class="grid small"><thead><tr><th>Tick</th><th>Raised by</th><th>Part</th><th>What</th><th>Rule</th>'
         '<th>Reason</th><th>Counts for this method</th></tr></thead><tbody>']
    for s in sigs:
        h.append("<tr><td>%s</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td></tr>" % (
            esc(s.get("t")), esc(signal_who(s)), esc({"program": "program", "ai": "AI"}.get(s.get("part"), s.get("part") or "-")), esc("block" if s.get("level") == "block" else s.get("level") or "flag"),
            esc(s.get("rule")), esc(s.get("reason")), "yes" if s.get("by") in counted else "no, extra"))
    h.append("</tbody></table>")
    return "".join(h)


def judge_html(run, vid):
    rows = [r for r in run.judge if r.get("visit_id") == vid]
    if not rows:
        return None
    kinds = {}
    for slot in run.texts_of.get(vid, {}).values():
        it = slot["row"].get("item") or {}
        kinds[it.get("item_id")] = it.get("kind")
    h = ['<table class="grid small"><thead><tr><th>Text</th><th>Rule</th><th>Judge\'s reading</th><th>Level the judge reported</th></tr></thead><tbody>']
    for r in sorted(rows, key=lambda r: (str(r.get("item_id")), r.get("rule") or 0)):
        h.append("<tr><td>%s</td><td>%s</td><td>%s</td><td>%s</td></tr>" % (
            esc(KIND_WORDS.get(kinds.get(r.get("item_id")), r.get("item_id"))), esc(r.get("rule")),
            esc(r.get("verdict")), esc(r.get("level", "-"))))
    h.append("</tbody></table>")
    return "".join(h)


def outcome_html(run, vid):
    planted = run.planted(vid)
    rules = run.rules()
    prule = planted.get("rule") if planted else None
    h = ['<table class="grid small"><thead><tr><th>Rule</th>']
    for c, name in METHODS.items():
        h.append('<th class="%s">%s</th>' % (METHOD_CLASS[c], esc(name)))
    h.append("</tr></thead><tbody>")
    dnf = g(run.scores or {}, "did_not_fire", default=[])
    for r in rules:
        h.append('<tr><th class="rule">Rule %d<span>%s</span></th>' % (r, esc(RULE_WORDS.get(r, ""))))
        for c in METHODS:
            rows = [a for a in run.attempts if a.get("visit_id") == vid and a.get("condition") == c and a.get("rule") == r]
            sigs = run.counting_signals(vid, c, r)
            if (vid, c) not in run.run_of:
                txt = "not run"
            elif rows:
                parts = []
                for a in rows:
                    o = a.get("outcome")
                    why = {"blocked": "it was stopped, so the rule held in this run",
                           "flagged": "it happened, and a flag names this rule",
                           "silent": "it happened, and nothing raised names this rule",
                           "did_not_fire": "the planted violation did not take effect in this case"}.get(o, "")
                    t = []
                    if a.get("break_t") is not None:
                        t.append("break at tick %s" % a["break_t"])
                    if a.get("signal_t") is not None:
                        t.append("first signal at tick %s" % a["signal_t"])
                    parts.append("<b>%s</b>: %s%s" % (esc(OUTCOME_WORDS.get(o, o)), esc(why),
                                                     (" (%s)" % esc(", ".join(t))) if t else ""))
                    if sigs and o in ("blocked", "flagged"):
                        parts.append('<span class="tech">%s</span>' % esc("; ".join(
                            "%s: %s" % (signal_who(s), s.get("reason")) for s in sigs[:2])))
                txt = "<br>".join(parts)
            elif prule == r and not run.scores:
                txt = "no scores file; signals: " + (esc(phrase_for(run, vid, c, [], planted)))
            elif sigs:
                txt = "<b>flag without a planted violation of this rule</b> (%s)" % esc(
                    "; ".join("%s: %s" % (signal_who(s), s.get("reason")) for s in sigs[:2]))
            else:
                txt = "nothing planted for this rule; nothing raised"
            h.append('<td class="%s">%s</td>' % (METHOD_CLASS[c], txt))
        h.append("</tr>")
    h.append("</tbody></table>")
    if any(a.get("visit_id") == vid and a.get("unpaired") for a in run.attempts):
        h.append('<p class="note"><b>No clean run of the same case to compare with</b> (the scorer marks a row of this case as unpaired).</p>')
    if isinstance(dnf, list) and any(
            (isinstance(x, dict) and x.get("visit_id") == vid) or x == vid for x in dnf):
        h.append('<p class="note"><b>The scorer lists this case as "did not take effect".</b></p>')
    return "".join(h)


def case_html(run, vid):
    planted = run.planted(vid)
    kind = ('<span class="plant">planted</span> %s' % esc(fault_kind_words(planted))) if planted else "clean case"
    h = ['<details class="case%s" id="%s"><summary><b>%s</b> &middot; %s</summary><div class="body">' % (
        " planted" if planted else "", anchor(run, vid), esc(vid), kind)]
    h.append("<h4>1. The texts, in the order of the flow</h4>" + texts_html(run, vid))
    h.append("<h4>2. What was planted</h4>" + planted_html(run, vid))
    h.append("<h4>3. The handovers: the method's own record against what really moved</h4>")
    for c, name in METHODS.items():
        what = "system's log" if c != "B" else "checker's record"
        h.append('<div class="meth %s"><h5>%s <span>(%s)</span></h5>%s</div>' % (
            METHOD_CLASS[c], esc(name), esc(what), handover_html(run, vid, c)))
    h.append("<h4>4. Every flag and block raised</h4>")
    for c, name in METHODS.items():
        h.append('<div class="meth %s"><h5>%s</h5>%s</div>' % (METHOD_CLASS[c], esc(name), signals_html(run, vid, c)))
    jh = judge_html(run, vid)
    if jh:
        h.append("<h4>5. The judge's readings of the advice texts</h4>" + jh)
    h.append("<h4>%s. The outcome per rule and method</h4>" % ("6" if jh else "5") + outcome_html(run, vid))
    h.append("</div></details>")
    return "".join(h)


# ------------------------------------------------------------------------------------------ the end part

def ends_html(run):
    h = []
    sc = run.scores or {}
    # cases left out
    lo = sc.get("left_out") if isinstance(sc.get("left_out"), dict) else None
    h.append("<h4>Cases left out, and why</h4>")
    items = []
    if isinstance(run.unusable, list) and run.unusable:
        for u in run.unusable:
            if isinstance(u, dict):
                items.append("%s: step %s, %s" % (esc(u.get("visit_id")), esc(u.get("step")), esc(u.get("reason"))))
    if lo and lo.get("visits"):
        items.append("the scorer leaves out %s case(s): %s" % (
            esc(lo.get("visits")), esc(json.dumps(lo.get("by_step_and_reason"), sort_keys=True))))
    dnf = sc.get("did_not_fire")
    if isinstance(dnf, list) and dnf:
        items.append("planted violations that did not take effect (kept in the run, scored as such): %s" % esc(
            ", ".join(str(x.get("fault_id", x)) if isinstance(x, dict) else str(x) for x in dnf)))
    h.append("<ul>%s</ul>" % "".join("<li>%s</li>" % i for i in items) if items else
             "<p>None. %s</p>" % ("" if run.scores else "(No scores file, so this is only what unusable_visits.json says.)"))
    # refusals
    h.append("<h4>Answers listed as possible refusals</h4>")
    if isinstance(run.candidates, list) and run.candidates:
        h.append('<table class="grid small"><thead><tr><th>Case</th><th>Step</th><th>Why listed</th><th>Confirmed by a person</th>'
                 "<th>First 300 characters</th></tr></thead><tbody>")
        for c in run.candidates:
            if isinstance(c, dict):
                h.append("<tr><td>%s</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td></tr>" % (
                    esc(c.get("visit_id")), esc(c.get("step")), esc(c.get("reason")),
                    "yes" if c.get("confirmed") else "no", esc(c.get("first_300"))))
        h.append("</tbody></table>")
    else:
        h.append("<p>None%s.</p>" % ("" if run.candidates is not None else " (the run folder has no refusal_candidates.json)"))
    # near misses
    h.append("<h4>Lines counted as near misses</h4>")
    nm = sc.get("action_near_misses")
    if isinstance(nm, dict) and nm:
        h.append("<p>Lines that look like an instruction to send something but name no known kind or place:</p><ul>%s</ul>" %
                 "".join("<li>%s: %s</li>" % (esc(k), esc(v)) for k, v in nm.items()))
    else:
        h.append("<p>None%s.</p>" % ("" if "action_near_misses" in sc else " (the scores give no such count)"))
    # AI calls
    h.append("<h4>AI calls by role</h4>")
    roles = Counter()
    by_cond = defaultdict(Counter)
    for r in run.ai_calls:
        pid = str(r.get("prompt_id") or "")
        name = pid.rsplit(".v", 1)[0]
        if name == "reviewer":
            role = "review"
        elif name == "watcher":
            role = "monitor"
        elif name == "judge":
            role = "judge"
        else:
            role = "steps"
        parts = str(r.get("run_id") or "").split(".")
        cond = parts[1] if len(parts) > 1 else "?"
        roles[role] += 1
        by_cond[role][cond] += 1
    judge_rows = len(run.judge)
    if judge_rows and not roles.get("judge"):
        roles["judge"] = judge_rows
        by_cond["judge"]["(judge.jsonl rows)"] = judge_rows
    if not roles:
        h.append("<p>No ai_calls.jsonl in this run folder.</p>")
    else:
        conds = [c for c in list(METHODS) + ["C", "(judge.jsonl rows)", "?"] if any(c in by_cond[r] for r in roles)]
        h.append('<table class="grid small"><thead><tr><th>Role</th><th>Calls</th>%s</tr></thead><tbody>' % "".join(
            "<th>%s</th>" % esc(METHODS.get(c, "C (Checked with proof; not a column here)" if c == "C" else c)) for c in conds))
        for role in ("steps", "monitor", "review", "judge"):
            if roles.get(role):
                h.append("<tr><td>%s</td><td><b>%d</b></td>%s</tr>" % (role, roles[role], "".join(
                    "<td>%d</td>" % by_cond[role].get(c, 0) for c in conds)))
        h.append("</tbody></table>")
        h.append('<p class="note">Steps: the AI steps of the flow (note writer, answer, plan, note for the patient). '
                 "Monitor: the monitor's AI under Monitored. Review: the review's AI after each case. Judge: the judge, "
                 "counted from ai_calls.jsonl or, when it holds none, from the rows of judge.jsonl.</p>")
    return "".join(h)


# ------------------------------------------------------------------------------------------ page

CSS = """
:root{--bg:#fbfaf7;--ink:#1f2328;--mute:#5b636b;--line:#dcd8cf;--card:#fff;--red:#c0262d;
--mp:#2563a8;--mm:#a8650b;--mc:#237a4b;--mpbg:#eaf1fa;--mmbg:#fbf1e2;--mcbg:#e6f4ec}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",Helvetica,Arial,sans-serif}
main{max-width:1180px;margin:0 auto;padding:16px 18px 60px}
h1{font-size:26px;margin:.6em 0 .2em}h2{font-size:21px;margin:1.8em 0 .4em;border-bottom:2px solid var(--line);padding-bottom:4px}
h3{font-size:17px;margin:1.4em 0 .3em}h4{font-size:15px;margin:1.2em 0 .3em}h5{font-size:14px;margin:.2em 0 .4em}h5 span{font-weight:400;color:var(--mute)}
.band{background:var(--red);color:#fff;font-weight:700;text-align:center;padding:12px 14px;font-size:17px;position:sticky;top:0;z-index:5}
.lede{color:var(--mute);margin:.2em 0 1em}
.facts{background:var(--card);border:1px solid var(--line);border-radius:8px;padding:10px 16px;margin:10px 0}
.facts dl{display:grid;grid-template-columns:max-content 1fr;gap:3px 16px;margin:4px 0}.facts dt{color:var(--mute)}.facts dd{margin:0}
table.grid{border-collapse:collapse;width:100%;background:var(--card);margin:8px 0;font-size:14px}
table.grid th,table.grid td{border:1px solid var(--line);padding:6px 8px;vertical-align:top;text-align:left}
table.grid thead th{background:#f1eee6}
table.grid.small{font-size:13px}
th.rule span{display:block;font-weight:400;color:var(--mute);font-size:12px}
th.mp,td.mp{border-top:3px solid var(--mp)}th.mm,td.mm{border-top:3px solid var(--mm)}th.mc,td.mc{border-top:3px solid var(--mc)}
thead th.mp{color:var(--mp);background:var(--mpbg)}thead th.mm{color:var(--mm);background:var(--mmbg)}thead th.mc{color:var(--mc);background:var(--mcbg)}
td.mp{background:#f7fafd}td.mm{background:#fdf9f1}td.mc{background:#f4faf6}
.n{display:inline-block;margin-right:10px}.n b{font-size:16px}.miss b,.miss{color:var(--red)}.tot,.fa,.tech,.note{color:var(--mute);font-size:12.5px}
.fa{display:block;margin-top:3px}.note{margin:.4em 0}
.plant{background:var(--red);color:#fff;border-radius:3px;padding:0 6px;font-size:12px;font-weight:700;text-transform:uppercase;letter-spacing:.03em}
b.plant{background:none;color:var(--red);padding:0;text-transform:none;font-size:inherit;letter-spacing:0}
details.case{background:var(--card);border:1px solid var(--line);border-radius:8px;margin:7px 0}
details.case.planted{border-left:5px solid var(--red)}
details.case>summary{cursor:pointer;padding:9px 14px;font-size:15px}
details.case .body{padding:2px 16px 14px;border-top:1px solid var(--line)}
details.fold{margin:6px 0}details.fold>summary{cursor:pointer;color:var(--mute)}
.text{margin:8px 0;border:1px solid var(--line);border-radius:6px;background:#fcfcfa}.text .th{padding:5px 10px;background:#f1eee6;font-size:13px}
pre.txt{margin:0;padding:8px 10px;white-space:pre-wrap;word-break:break-word;font:12.5px/1.45 ui-monospace,Menlo,Consolas,monospace}
details.more summary{cursor:pointer;padding:3px 10px;color:var(--mute);font-size:13px}
.meth{border-left:4px solid var(--line);padding-left:10px;margin:8px 0}.meth.mp{border-color:var(--mp)}.meth.mm{border-color:var(--mm)}.meth.mc{border-color:var(--mc)}
.meth.mp h5{color:var(--mp)}.meth.mm h5{color:var(--mm)}.meth.mc h5{color:var(--mc)}
tr.differs td{background:#fdecec}.diff{color:var(--red);font-size:12px}
.howto ul{margin:6px 0 2px;padding-left:20px}.grade{display:inline-block;background:#eee9dd;border-radius:3px;padding:0 6px;font-size:12px;font-weight:700;margin-bottom:3px}
.legend{display:flex;gap:16px;flex-wrap:wrap;font-size:13px;margin:8px 0}.legend span{padding-left:8px}
.legend .mp{border-left:4px solid var(--mp)}.legend .mm{border-left:4px solid var(--mm)}.legend .mc{border-left:4px solid var(--mc)}
button.tog{font:inherit;font-size:13px;padding:3px 10px;margin:4px 6px 4px 0;border:1px solid var(--line);background:var(--card);border-radius:5px;cursor:pointer}
a{color:#1d4f91}
@media (max-width:700px){main{padding:10px}table.grid{font-size:12.5px}.facts dl{grid-template-columns:1fr}}
@media print{.band{position:static}details.case{break-inside:avoid}}
"""

JS = """
function setAll(id,open){var ds=document.querySelectorAll('#'+id+' details.case');for(var i=0;i<ds.length;i++){ds[i].open=open;}}
"""


def when_made(run):
    p = run.dir / "manifest.json"
    try:
        return datetime.datetime.fromtimestamp(p.stat().st_mtime).strftime("%d %b %Y, %H:%M")
    except OSError:
        return None


def header_html(runs):
    h = []
    stand = [r for r in runs if r.is_stand_in()]
    if stand:
        h.append('<div class="band">%s</div>' % esc(STAND_IN_BAND))
    h.append("<main>")
    h.append("<h1>Run report</h1>")
    exps = sorted({r.experiment for r in runs})
    h.append('<p class="lede">What happened in each case of the run, under the three methods: '
             "<b class=\"mpt\">Promised</b>, <b class=\"mmt\">Monitored</b> and <b class=\"mct\">Checked</b>.</p>")
    h.append('<div class="legend"><span class="mp">Promised: %s</span><span class="mm">Monitored: %s</span>'
             '<span class="mc">Checked: %s</span><span><span class="plant">planted</span> marks a violation that '
             "the test bench caused on purpose</span></div>" % (esc(METHOD_SAYS["A"]), esc(METHOD_SAYS["A+"]), esc(METHOD_SAYS["B"])))
    h.append('<div class="facts howto"><b>How to read this page</b><ul>'
             "<li><b>A case</b> is one input that runs once through one flow: one conversation in Experiment 1, one question in Experiment 2.</li>"
             "<li><b>Planted</b> means the test bench broke a rule on purpose in that case, so we know what the methods should catch. "
             "A <b>clean</b> case has nothing planted.</li>"
             "<li><b>Promised</b>: the vendor promises, the AI steps are told the rules, and a review reads the log and texts after the case.</li>"
             "<li><b>Monitored</b>: Promised plus a monitor that reads every message between two steps; it can raise a flag and cannot stop anything.</li>"
             "<li><b>Checked</b>: every piece of content has a label and a checker program compares each handover with it; it can stop a handover and it writes the record.</li>"
             "<li><b>Blocked</b>: the method stopped the violation. <b>Flagged</b>: it happened and the method raised a flag. "
             "<b>Missed</b>: it happened and the method raised nothing. A <b>false alarm</b> is a flag on a clean case.</li>"
             "</ul></div>")
    h.append('<div class="facts"><dl>')
    h.append("<dt>Experiments</dt><dd>%s</dd>" % esc("; ".join(EXPERIMENT_NAMES.get(e, "Experiment %s" % e) for e in exps)))
    for r in runs:
        counts = r.manifest.get("counts") if isinstance(r.manifest.get("counts"), dict) else {}
        total = counts.get("cases", len(r.case_ids))
        clean = counts.get("clean_cases")
        if clean is None:
            clean = sum(1 for v in r.case_ids if not r.planted(v))
        pl = counts.get("faults_planned")
        if pl is None:
            pl = sum(1 for v in r.case_ids if r.planted(v))
        made = when_made(r)
        h.append("<dt>%s</dt><dd>Experiment %s &middot; %s cases: %s clean, %s with a planted violation &middot; run made %s "
                 "&middot; texts written by: <b>%s</b>%s</dd>" % (
                     esc(r.name), esc(r.experiment), esc(total), esc(clean), esc(pl),
                     esc(made) + " (time the manifest was saved; the manifest holds no date)" if made else "date not known",
                     esc(r.ai_kind()), "" if r.scores else " &middot; no scores file"))
    h.append("</dl></div>")
    return "".join(h)


def build_page(runs):
    out = ["<!doctype html><html lang=\"en\"><head><meta charset=\"utf-8\"><meta name=\"viewport\" "
           "content=\"width=device-width,initial-scale=1\"><title>Run report</title><style>%s</style></head><body>" % CSS]
    out.append(header_html(runs))
    for i, run in enumerate(runs):
        sec = "run%d" % i
        out.append('<section id="%s"><h2>%s</h2>' % (sec, esc(EXPERIMENT_NAMES.get(run.experiment, "Experiment")) + " &middot; " + esc(run.name)
                                                       if False else esc(EXPERIMENT_NAMES.get(run.experiment, "Experiment")) + " (" + esc(run.name) + ")"))
        if run.is_stand_in():
            out.append('<p class="note"><b>%s</b></p>' % esc(STAND_IN_BAND))
        out.append("<h3>Summary: what the methods did with the planted violations</h3>")
        out.append(safe(summary_html, run))
        out.append("<h3>The cases</h3>")
        out.append(safe(case_table_html, run))
        out.append("<h3>Case by case</h3>")
        out.append('<button class="tog" type="button" onclick="setAll(\'%s\',true)">open all</button>'
                   '<button class="tog" type="button" onclick="setAll(\'%s\',false)">close all</button>' % (sec, sec))
        for vid in run.case_ids:
            out.append(safe(case_html, run, vid))
        out.append("<h3>At the end</h3>")
        out.append(safe(ends_html, run))
        out.append("</section>")
    out.append("</main><script>%s</script></body></html>" % JS)
    return "".join(out)


def safe(fn, *args):
    """A section that cannot be built says so; it never stops the page."""
    try:
        return fn(*args)
    except Exception as exc:  # noqa: BLE001
        return '<p class="note">This part could not be built (%s: %s).</p>' % (esc(type(exc).__name__), esc(exc))


def main(argv=None):
    ap = argparse.ArgumentParser(description="One self-contained HTML page that shows a run case by case.")
    ap.add_argument("folders", nargs="+", help="run folder(s), for example runs/trial_e1 runs/trial_e2")
    ap.add_argument("--out", required=True, help="the HTML file to write")
    a = ap.parse_args(argv)
    cfg = load_config()
    runs = []
    for f in a.folders:
        p = Path(f)
        if not p.is_dir():
            print("not a folder: %s" % f, file=sys.stderr)
            return 2
        runs.append(Run(p, cfg))
    runs.sort(key=lambda r: (r.experiment, r.name))
    page = build_page(runs)
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(page, encoding="utf-8")
    print("wrote %s (%d bytes; %d cases)" % (out, len(page.encode("utf-8")), sum(len(r.case_ids) for r in runs)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
