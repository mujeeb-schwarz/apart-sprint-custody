"""Piece 2: puts each of the outside model's sealed ideas (opened with tools/outside_texts.py) into one group and
writes ideas_compared.md. No model is called. The group B fault definitions are checked for form only
(custody.faults.check_fault); they are never run.
Run from the artefact root:  PYTHONDONTWRITEBYTECODE=1 python3 night/ideas/ideas_compare.py
"""
import json, re, sys
from collections import Counter, OrderedDict
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from custody import assemble, datasets, faults

HERE = Path(__file__).parent
UNNAMED = ("analytics", "training_store", "outside_annotator", "debug_bucket")
DUTY_AT = {"d3": ("transcriber", "transcript", 2), "d4": ("note_writer", "transcript", 4),
           "d5": ("note_writer", "note_draft", 5), "d6": ("record", "note_draft", 6)}
SEND_LINE = {"w2": (1, "transcriber", "transcript", "transcriber", "note_writer"),
             "w3": (3, "note_writer", "note_draft", "note_writer", "record")}
EVENT_LINE = {"w2c": ("resume", "w2", 1, "transcriber", "transcript", "transcriber", "note_writer_cache"),
              "w3q": ("timeout", "w3", 3, "note_writer", "note_draft", "note_writer", "note_writer_queue")}
SIDE_DEL = {"cache": ("resume", "w2", 3, "r2", "transcript", "note_writer_cache"),
            "queue": ("timeout", "w3", 5, "r1", "note_draft", "note_writer_queue")}

defs = OrderedDict()   # fault definitions for group B, keyed by a short name


def short(s, n=70):
    return s if len(s) <= n else s[:n - 1] + "..."


def fault(fid, rule, says, ops, patch=None, events=None):
    return {"fault_id": fid, "kind": "wiring" if patch else "step", "rule": rule, "says": says, "ops": ops,
            "patch": patch or [], "events": events or [], "needs": {}}


def add_def(key, f):
    defs.setdefault(key, f)
    return key


def classify(n, line):
    p = [x.strip() for x in line.split("|")]
    rule = int(p[0].split()[1]); step = p[1].split(": ", 1)[1]
    what = p[2].split(": ", 1)[1]; log = p[3].split(": ", 1)[1]
    m = re.match(r"(\w+) copied to (\w+)$", what)
    # ---------------------------------------------------------------- rule 1
    if rule == 1:
        kind, to = m.group(1), m.group(2)
        if to in UNNAMED:
            return "A", "rule 1: extra send logged (step %s, %s to %s)" % (step, kind, to)
        key = add_def("r1_%s_%s_%s" % (step, kind, to), fault(
            "IDEA.r1.%s.%s.%s" % (step, kind, to), 1,
            "The step %s also sends its copy of the %s to %s, which is a named place that may not hold a %s, and the system's own log shows the send." % (step, kind, to, kind),
            [{"op": "extra_send", "step": step, "kind": kind, "to": to, "logged": True}]))
        return "B", "extra_send {step %s, kind %s, to %s (a named place that may not hold it), logged true}; our list only sends to the four unnamed stores" % (step, kind, to)
    # ---------------------------------------------------------------- rule 2
    if rule == 2:
        mm = re.search(r"\b(d[3-6])\b", log)
        side = "cache" if "note_writer_cache" in what else ("queue" if "note_writer_queue" in what else None)
        if side is None:
            pk = re.match(r"(\w+) at (\w+)", what)
            d = {(v[0], v[1]): k for k, v in DUTY_AT.items()}[(pk.group(2), pk.group(1))]
            if log.startswith("accurate late"):
                return "A", "rule 2: late delete (%s)" % d
            if log.startswith("no "):
                return "A", "rule 2: skip delete (%s)" % d
            if log.startswith("invented timely"):
                return "A", "rule 2: skip delete and the log says it happened (%s)" % d
            if "timer restarts" in what:
                return "A", "rule 2: late delete (%s); same planted result: the bench counts the hold from the earliest arrival, so a restarted timer is not a separate violation" % d
        else:
            ev, at, pos, det, kind, place = SIDE_DEL[side]
            if log.startswith("w2c without") or log.startswith("w3q without"):
                add_def("r2_skip_" + det, fault("IDEA.r2.skip_%s" % det, 2,
                        "On the %s event the %s copy at %s is never deleted." % (ev, kind, place),
                        [{"op": "skip_delete", "duty": det}], events=[{"on": ev, "at": at}]))
                return "B", "skip_delete {duty %s} with the event %s@%s (a detour deletion; our list skips only d3 to d6; the wiring faults F2 and PF10 do the same by patch)" % (det, ev, at)
            if log.startswith("invented timely"):
                return "C", "needs a log line that claims a deletion at %s; claim_delete accepts only a duty of the wiring and %s is a detour step, not a duty" % (place, det)
            return "C", "a late deletion of a copy in a detour store: the close sweep runs only the duties, so a skipped %s deletion is never made up (nothing to log, no late line)" % det
    # ---------------------------------------------------------------- rule 3
    if rule == 3:
        # a. extra sends (rule 1 content hidden from the log)
        mm = re.match(r"(\w+) copied from (\w+) to (\w+)$", what)
        if mm:
            kind, frm, to = mm.groups()
            if log.startswith("unauthorized handover omitted"):
                return "A", "rule 1: extra send not logged (step %s, %s to %s)" % (step, kind, to)
            if "destination falsely says" in log:
                return "A", "rule 1: extra send, log names a harmless place (step %s, %s to %s)" % (step, kind, to)
            if "content falsely says" in log:
                new = log.split("says ")[1]
                add_def("r3_masked_kind", fault("IDEA.r3.record.note.analytics.kind_masked", 3,
                        "The step record sends its copy of the note to analytics and the system's own log shows the send, but names the kind as note_draft.",
                        [{"op": "extra_send", "step": "record", "kind": "note", "to": "analytics", "logged": True},
                         {"op": "false_log", "step": "record", "kind": "note", "change": {"kind": new}}]))
                return "B", "extra_send {record, note, analytics, logged true} + false_log {change kind: note_draft}; our list has no false log on a sent note and none that changes the kind of an extra send"
        # b. note deletion (no duty deletes a note)
        if what.startswith("note deleted at record") or what.startswith("note remains at record"):
            add_def("r3_note_duty", fault("IDEA.r3.note_duty_hidden", 3,
                    "A duty deletes the note at the record after the filing step, and the system's own log has no line for it.",
                    [{"op": "edit_record", "mode": "drop", "position": 7}],
                    patch=[{"op": "add", "path": "/plumbing/duties/-", "value": {"id": "d99", "kind": "note", "place": "record", "after_step": "record"}}]))
            if what.startswith("note deleted"):
                return "B", "a wiring patch that adds a duty deleting the note (after_step record), plus edit_record {mode drop} on its line; untested, and it changes the flow (a real note deletion)"
            return "B", "a wiring patch that adds a duty for the note, skip_delete on it and false_log claim_delete: the same added duty; untested"
        # c. log lines of moves, duties and detours
        mid = re.search(r"\b(w2c|w3q|w2|w3)\b", what + " " + log)
        did = re.search(r"\b(d3|d4|d5|d6)\b", what + " " + log)
        inv = log.startswith("invented") and "handover" in log and what.startswith("no ")
        if "handover" in what or what.startswith("w") or "sent" in what or "enters" in what:
            # find which move
            if mid:
                mv = mid.group(1)
            elif "note_writer_queue" in what:
                mv = "w3q"
            elif "note_writer_cache" in what:
                mv = "w2c"
            else:
                mv = "w3" if "note_draft" in what else "w2"
            if inv:
                if mv in ("w2c", "w3q"):
                    return "A", "rule 3: entry added (a line for a handover that did not happen: %s to %s)" % (EVENT_LINE[mv][5], EVENT_LINE[mv][6])
                return "C", "no operation removes the real %s handover and lets the flow go on: the log line is there, so the handover would have to be stopped, and then the note is never made (a wiring patch that removes the move breaks the case)" % mv
            if "two separate" in log or "second handover" in log or "only first" in log:
                if mv in SEND_LINE:
                    pos, st, kind, frm, to = SEND_LINE[mv]
                    ev = [{"on": "timeout", "at": "w3"}] if "only first" in log else []
                else:
                    ev0, at, pos, st, kind, frm, to = EVENT_LINE[mv]
                    ev = [{"on": ev0, "at": at}]
                if "only first" in log:
                    pos = 4
                    add_def("r3_drop_second_w3", fault("IDEA.r3.w3.second_send_missing", 3,
                            "After the draft send times out and is sent again, the system's own log has only the first handover.",
                            [{"op": "edit_record", "mode": "drop", "position": 4}], events=ev))
                    return "B", "edit_record {mode drop, position 4} on the log with the event timeout@w3 (our entry_removed drops the first matching send line only, with no event)"
                key = add_def("r3_dup_" + mv, fault("IDEA.r3.%s.duplicate_line" % mv, 3,
                              "The log shows the handover %s twice; it happened once." % mv,
                              [{"op": "false_log", "mode": "add", "position": pos + 1, "step": st, "kind": kind, "from": frm, "to": to}], events=ev))
                return "B", "false_log {mode add, a second %s line (%s to %s)}%s; our added lines are never a copy of a real handover" % (mv, frm, to, (" with the event %s@%s" % (ev[0]["on"], ev[0]["at"])) if ev else "")
            if mv in SEND_LINE:
                pos, st, kind, frm, to = SEND_LINE[mv]
                if "line missing" in log:
                    return "A", "rule 3: entry removed (%s)" % mv
                if "time" in log:
                    return "A", "rule 3: entry changed, time (%s)" % mv
                if "destination" in log:
                    return "A", "rule 3: entry changed, destination (%s)" % mv
                if "content" in log:
                    return "A", "rule 3: entry changed, kind (%s)" % mv
                if "source" in log:
                    new = re.search(r"says (\w+)", log).group(1)
                    add_def("r3_from_" + mv, fault("IDEA.r3.%s.source_changed" % mv, 3,
                            "The log line for %s names %s as the sender." % (mv, new),
                            [{"op": "false_log", "step": st, "kind": kind, "change": {"from": new}}]))
                    return "B", "false_log {step %s, kind %s, change from: %s}; our changes are destination, kind and time only" % (st, kind, new)
            else:
                ev0, at, pos, st, kind, frm, to = EVENT_LINE[mv]
                ev = [{"on": ev0, "at": at}]
                if "line missing" in log:
                    ch = None; desc = "false_log {change null}"
                elif "time" in log:
                    ch = {"t": 0}; desc = "false_log {change t}"
                else:
                    fld, new = ("from", re.search(r"says (\w+)", log).group(1)) if "source" in log else \
                               (("to", re.search(r"says (\w+)", log).group(1)) if "destination" in log else
                                ("kind", re.search(r"says (\w+)", log).group(1)))
                    ch = {fld: new}; desc = "false_log {change %s: %s}" % (fld, new)
                key = add_def("r3_%s_%s" % (mv, "drop" if ch is None else "_".join(sorted(ch))), fault(
                    "IDEA.r3.%s.%s" % (mv, "line_missing" if ch is None else "changed_" + "_".join(sorted(ch))), 3,
                    "On the %s event the log line for %s is %s." % (ev0, mv, "missing" if ch is None else "changed (%s)" % json.dumps(ch)),
                    [{"op": "false_log", "step": st, "kind": kind, "change": ch}], events=ev))
                return "B", "%s on the rare-event handover %s with the event %s@%s (the first matching send line is %s); our list changes only the two normal handovers, with no event" % (desc, mv, ev0, at, mv)
        # d. deletion lines
        side = "cache" if "note_writer_cache" in what else ("queue" if "note_writer_queue" in what else None)
        if side:
            ev, at, pos, det, kind, place = SIDE_DEL[side]
            if log.startswith("invented") or "two separate" in log:
                return "C", "needs a log line that claims or repeats a deletion at %s; claim_delete accepts only a duty of the wiring (%s is a detour step), and add and edit_record add only create send lines" % (place, det)
            e = [{"on": ev, "at": at}]
            if "missing" in log:
                add_def("r3_drop_" + det, fault("IDEA.r3.%s.deletion_line_missing" % det, 3,
                        "On the %s event the log has no line for the deletion at %s." % (ev, place),
                        [{"op": "edit_record", "mode": "drop", "position": pos}], events=e))
                return "B", "edit_record {mode drop, position %d} with the event %s@%s" % (pos, ev, at)
            fld = "t" if "time" in log else ("from" if "place" in log else "kind")
            new = {"t": 0, "from": "note_writer", "kind": "note_draft" if kind == "transcript" else "transcript"}[fld]
            add_def("r3_%s_%s" % (det, fld), fault("IDEA.r3.%s.deletion_line_%s" % (det, fld), 3,
                    "On the %s event the log line for the deletion at %s has the wrong %s." % (ev, place, fld),
                    [{"op": "edit_record", "position": pos, "field": fld, "value": new}], events=e))
            return "B", "edit_record {position %d, field %s} with the event %s@%s" % (pos, fld, ev, at)
        d = did.group(1) if did else re.search(r"\b(d[3-6])\b", log).group(1)
        place, kind, pos = DUTY_AT[d]
        if "remains" in what and "invented" in log:
            return "A", "rule 2: skip delete and the log says it happened (%s); our list files this under rule 2" % d
        if "two separate" in log:
            add_def("r3_dup_" + d, fault("IDEA.r3.%s.deletion_logged_twice" % d, 3,
                    "The deletion by %s happens once and the log shows it twice." % d,
                    [{"op": "false_log", "mode": "claim_delete", "duty": d}]))
            return "B", "false_log {mode claim_delete, duty %s} with no skip_delete (the real line stays, a second is added); our claim_delete always stands beside a skip_delete" % d
        if "missing" in log:
            add_def("r3_drop_" + d, fault("IDEA.r3.%s.deletion_line_missing" % d, 3,
                    "The deletion by %s happens and the log has no line for it." % d, [{"op": "edit_record", "mode": "drop", "position": pos}]))
            return "B", "edit_record {mode drop, position %d} (the line of %s); our entry_removed drops send lines only" % (pos, d)
        fld = "t" if "time" in log else ("from" if "place" in log else "kind")
        new = {"t": 0, "from": "transcriber" if place != "transcriber" else "note_writer", "kind": "note_draft" if kind == "transcript" else "transcript"}[fld]
        add_def("r3_%s_%s" % (d, fld), fault("IDEA.r3.%s.deletion_line_%s" % (d, fld), 3,
                "The deletion by %s happens and its log line has the wrong %s." % (d, {"t": "time", "from": "place", "kind": "content"}[fld]),
                [{"op": "edit_record", "position": pos, "field": fld, "value": new}]))
        return "B", "edit_record {position %d, field %s} on the line of %s; our changes touch send lines only" % (pos, fld, d)
    raise ValueError(line)


def main():
    lines = [l for l in (HERE / "ideas_opened_output.txt").read_text().splitlines() if l.strip()]
    rows = []
    for i, l in enumerate(lines, 1):
        g, why = classify(i, l)
        p = [x.strip() for x in l.split("|")]
        words = "%s; %s; log: %s" % (p[1].split(": ", 1)[1], p[2].split(": ", 1)[1], p[3].split(": ", 1)[1])
        rows.append((i, p[0].replace("RULE ", ""), words, g, why))
    cnt = Counter(r[3] for r in rows)
    byrule = Counter((r[1], r[3]) for r in rows)
    # check the form of the group B definitions (not run)
    choices = datasets.default_choices(); wiring = assemble.load_wiring()
    bad = []
    for k, f in defs.items():
        try:
            faults.check_fault(f, wiring, choices)
        except Exception as e:
            bad.append("%s: %s" % (k, e))
    out = ["# The outside model's sealed ideas against our list of plantable violations", "",
           "Opened Sat 14 Nov 2026 with `python3 tools/outside_texts.py ideas --out sealed/ideas_exp1.json --open --freeze-file live_night_e1/frozen.json` (it only prints the file and renames the seal marker `ideas_exp1.json.sealed` to `.opened`; no model is called). The file holds %d ideas (rule 1: %d, rule 2: %d, rule 3: %d). Our list is `plans/test/exp1_catalogue.json` (90 variants). Every idea is in exactly one group." % (
               len(rows), sum(1 for r in rows if r[1] == "1"), sum(1 for r in rows if r[1] == "2"), sum(1 for r in rows if r[1] == "3")), "",
           "## Counts", "",
           "| Group | Meaning | All | Rule 1 | Rule 2 | Rule 3 |", "|---|---|---|---|---|---|"]
    meaning = {"A": "already in our list", "B": "not in our list; the bench can plant it with its existing operations",
               "C": "not in our list; the bench cannot plant it"}
    for g in "ABC":
        out.append("| %s | %s | %d | %d | %d | %d |" % (g, meaning[g], cnt[g], byrule[("1", g)], byrule[("2", g)], byrule[("3", g)]))
    out += ["", "Reading the groups:", "",
            "- Group A is large because the model was given the step names, the places and the duties, so it wrote the same kinds of break that our list was built from. Four of its rule 2 ideas ('timer restarts') are the same planted result as a late delete: the bench counts a copy's age from its earliest arrival, so they are filed under late delete.",
            "- Nine ideas in group A are rule 3 ideas whose planted result is a rule 2 or rule 1 kind in our list (a deletion that did not happen but the log says it did; an extra send the log leaves out or names wrongly).",
            "- Group B is mostly the same kinds as ours, but aimed at a line our list never touches: the log line of a deletion, the source field, the lines of the rare-event handovers (resume, timeout), a duplicated line, and sends to a named place that may not hold the kind.",
            "- Group C is what the bench has no operation for: a log line claiming a deletion at a store that no duty empties (the cache and the queue), a late deletion in those stores, and a handover that is logged while the real one is stopped.", "",
            "## One row for each idea", "",
            "Words: step; what is sent, kept or changed; what the log shows (shortened).", "",
            "| # | Rule | The idea | Group | Our kind, or the operations, or what is missing |", "|---|---|---|---|---|"]
    for i, r, w, g, why in rows:
        out.append("| %d | %s | %s | %s | %s |" % (i, r, short(w.replace("|", "/"), 110), g, why.replace("|", "/")))
    out += ["", "## Group B as fault definitions (not run)", "",
            "Form checked with `custody.faults.check_fault` against the wiring and the design choices (it raised nothing for %d of %d definitions%s). Positions in `edit_record` and `false_log add` are the places in the system's own log of the practice case c0001 (see `clean_logs_output.txt`: no event, timeout@w3, resume@w2); under Checked the same `edit_record` edits the checker's record (its own numbering), so those positions would be set again. Twelve families are shown once; the full set of %d is built and checked by `ideas_compare.py`, and the rest of a family changes the step, kind, place or position." % (
                len(defs) - len(bad), len(defs), ("; failed: " + "; ".join(bad)) if bad else "", len(defs)), ""]
    show = ["r1_note_writer_note_draft_note_writer_cache", "r1_record_note_note_writer", "r2_skip_r1", "r3_from_w2", "r3_dup_w2",
            "r3_w2c_drop", "r3_drop_second_w3", "r3_drop_d3", "r3_d3_t", "r3_dup_d3", "r3_r1_drop", "r3_masked_kind", "r3_note_duty"]
    for k, f in defs.items():
        if k not in show:
            continue
        out += ["`%s`" % k, "```json", json.dumps(f, indent=1), "```", ""]
    (HERE / "ideas_compared.md").write_text("\n".join(out), encoding="utf-8")
    print(dict(cnt), dict(byrule), "defs", len(defs), "bad", bad)


main()
