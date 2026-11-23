import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from custody import score, stats  # noqa: E402
from custody.core import canon, claim_level, has_ai_mark, normalise_id, sources_named  # noqa: E402

D = json.load(open(str(ROOT / "config" / "design_choices.json"), encoding="utf-8"))
W = json.load(open(str(ROOT / "wiring" / "wiring.json"), encoding="utf-8"))
DR = copy.deepcopy(D)
DR["rules"]["key_source"] = "readers"  # the older behaviour (the program's readers are the key), for tests of it

GOOD = "Claim: The treatment may reduce the outcome. [source: pmid:1]\n[AI-generated]"
NOMARK = "Claim: The treatment may reduce the outcome. [source: pmid:1]"


class Store:
    """A hand-made run folder (Version 2: three methods A, A+, B; the judge file holds the answer key)."""

    def __init__(self, root):
        self.root = Path(root)
        self.rows = {k: [] for k in ("results", "signals", "texts", "own_log", "visits", "truth", "plan", "judge")}
        self.journal = {}
        self.seq = 0

    def visit(self, vid, conv, split, grade="low", fault=None, clean_of=None, experiment=None):
        v = {"visit_id": vid, "conversation_id": conv, "split": split,
             "expert_certainty": grade, "given_answer": None, "given_by": None,
             "evidence": [{"source_id": "pmid:1", "title": "t", "text": "x"}]}
        if clean_of:
            v["clean_of"] = clean_of
        if experiment:
            v["experiment"] = experiment
        self.rows["visits"].append(v)
        self.rows["plan"].append({"visit_id": vid, "fault": fault})

    def run(self, vid, conv, split, cond, events=(), signals=(), texts=None, own_log=(), crashed=False, journal=None):
        """signals: (rule, level, by, t) or (rule, level, by, t, extra) where extra holds handover_id, item_ids, part."""
        rid = "%s.%s.r0" % (vid, cond)
        self.rows["results"].append({"run_id": rid, "visit_id": vid, "conversation_id": conv,
                                     "condition": cond, "rep": 0, "split": split,
                                     "produced": {"note": True, "patient_note": True},
                                     "crashed": crashed})
        for (kind, t, place, to, item, hid, detail) in events:
            self.seq += 1
            self.rows["truth"].append({"seq": self.seq, "run_id": rid, "t": t, "kind": kind, "step": "s",
                                       "place": place, "to_place": to, "item_id": item, "handover_id": hid,
                                       "fault_id": None, "detail": detail})
        for sg in signals:
            rule, level, by, t = sg[:4]
            extra = sg[4] if len(sg) > 4 else {}
            row = {"run_id": rid, "t": t, "rule": rule, "level": level, "by": by,
                   "handover_id": None, "item_ids": [], "reason": "r", "part": "program"}
            row.update(extra)
            self.rows["signals"].append(row)
        for i, (kind, text) in enumerate((texts if texts is not None else [("patient_note", GOOD)])):
            self.rows["texts"].append({"run_id": rid, "place": "patient", "t": 20 + i,
                                       "item": {"item_id": "%s-%s" % (rid, kind), "visit_id": vid,
                                                "kind": kind, "text": text, "made_by": "s", "parents": []}})
        for ln in own_log:
            self.rows["own_log"].append(dict(ln, run_id=rid))
        if journal is not None:
            self.journal[rid] = journal

    def auto_judge(self, skip=(), **override):
        """Judge rows as a perfect judge would write them for the hand-made texts (the readers read them).
        override: {item_id: {4: verdict, 5: level, 6: verdict}} to say something else."""
        visits = {v["visit_id"]: v for v in self.rows["visits"]}
        done = {(j["item_id"], int(j["rule"])) for j in self.rows["judge"]}
        for row in self.rows["texts"]:
            it = row["item"]
            if it["kind"] not in ("answer", "plan", "patient_note") or it["item_id"] in skip:
                continue
            ov = override.get(it["item_id"], {})
            truth = {normalise_id(x["source_id"]) for x in visits[it["visit_id"]]["evidence"]}
            names = sources_named(it["text"], D)
            v4 = ov.get(4) or ("kept" if names and all(n in truth for n in names) else "broken")
            v6 = ov.get(6) or ("kept" if has_ai_mark(it["text"], D) else "broken")
            lvl = ov.get(5) or claim_level(it["text"], D) or "none"
            grade = visits[it["visit_id"]].get("expert_certainty")
            v5 = "undecided" if lvl == "none" or grade is None else ("kept" if lvl == grade else "broken")
            for rule, verdict in ((4, v4), (5, v5), (6, v6)):
                if (it["item_id"], rule) in done:
                    continue
                row5 = {"visit_id": it["visit_id"], "item_id": it["item_id"], "rule": rule, "verdict": verdict,
                        "judge": "live", "prompt_id": "judge.v1"}
                if rule == 5:
                    row5["level"] = lvl
                self.rows["judge"].append(row5)

    def write(self):
        (self.root / "hidden").mkdir(parents=True, exist_ok=True)
        paths = {"results": "results.jsonl", "signals": "signals.jsonl", "texts": "texts.jsonl",
                 "own_log": "own_log.jsonl", "visits": "visits.jsonl",
                 "truth": "hidden/truth.jsonl", "plan": "hidden/plan.jsonl"}
        for k, name in paths.items():
            (self.root / name).write_text("".join(canon(r) + "\n" for r in self.rows[k]), encoding="utf-8")
        if self.rows["judge"]:
            (self.root / "judge.jsonl").write_text("".join(canon(r) + "\n" for r in self.rows["judge"]), encoding="utf-8")
        if self.journal:
            (self.root / "journal").mkdir(exist_ok=True)
            for rid, recs in self.journal.items():
                (self.root / "journal" / ("%s.jsonl" % rid)).write_text("".join(canon(r) + "\n" for r in recs), encoding="utf-8")


def send(t, to, hid, item="i1", kind="transcript"):
    return [("asked", t, "transcriber", to, item, hid, {"action": "send", "kind": kind}),
            ("moved", t, "transcriber", to, item, hid, {"action": "send", "kind": kind})]


def log_line(hid, t=3, to="note_writer", item="i1", kind="transcript", action="send", frm="transcriber"):
    return {"handover_id": hid, "action": action, "from": frm, "to": to, "item_ids": [item], "kind": kind, "t": t}


def journal_rec(hid, t=3, to="note_writer", item="i1", kind="transcript", decision="deliver", action="send", frm="transcriber"):
    return {"seq": 0, "t": t, "decision": decision,
            "handover": {"handover_id": hid, "action": action, "from_place": frm, "to_place": to, "item_ids": [item],
                         "kind": kind, "t": t, "step": "s", "move_id": None, "run_id": "r"}}


ASKED_ONLY = [("asked", 3, "transcriber", "analytics", "i1", "h1", {"action": "send", "kind": "transcript"})]
F1 = {"fault_id": "F1", "rule": 1, "ops": [{"op": "extra_send", "step": "s", "kind": "transcript", "to": "analytics",
                                            "logged": True}]}
F6 = {"fault_id": "F6", "rule": 6, "ops": [{"op": "rewrite", "step": "patient_note", "mode": "drop_ai_mark"}]}


class Facts(unittest.TestCase):
    def facts(self, events, own_log, cond, journal=None):
        evs = []
        for i, (kind, t, place, to, item, hid, detail) in enumerate(events):
            evs.append({"seq": i, "run_id": "r", "t": t, "kind": kind, "place": place, "to_place": to,
                        "item_id": item, "handover_id": hid, "fault_id": None, "detail": detail})
        return score.rule_facts(evs, own_log, cond, W, D, journal)

    def test_rule_1(self):
        self.assertTrue(self.facts(send(3, "analytics", "h1"), [], "A")[1]["broken"])
        self.assertFalse(self.facts(send(3, "note_writer", "h1"), [], "A")[1]["broken"])
        f = self.facts(ASKED_ONLY, [], "B")
        self.assertFalse(f[1]["broken"])
        self.assertTrue(f[1]["refused"])

    def test_rule_2(self):
        arrive = [("made", 4, "transcriber", None, "i1", None, {"kind": "transcript"})]
        ontime = arrive + [("moved", 14, "transcriber", None, "i1", "h2", {"action": "delete", "kind": "transcript"})]
        self.assertTrue(self.facts(arrive, [], "A")[2]["broken"])
        self.assertFalse(self.facts(ontime, [], "A")[2]["broken"])
        kept = [("kept", 4, "transcriber", None, "k1", None, {"kind": "transcript", "of": "i0"})]
        self.assertTrue(self.facts(kept, [], "B")[2]["broken"])

    def test_rule_2_late_delete_is_broken(self):
        arrive = [("made", 4, "transcriber", None, "i1", None, {"kind": "transcript"})]
        late = arrive + [("moved", 15, "transcriber", None, "i1", "h2", {"action": "delete", "kind": "transcript"})]
        self.assertTrue(self.facts(late, [], "A")[2]["broken"])

    def test_rule_3_compares_the_record_the_method_relies_on_with_what_moved(self):
        mv = send(3, "note_writer", "h1")
        line = log_line("h1")
        rec = journal_rec("h1")
        self.assertFalse(self.facts(mv, [line], "A")[3]["broken"])
        self.assertTrue(self.facts(mv, [], "A")[3]["broken"])
        self.assertTrue(self.facts(mv, [], "B", [])[3]["broken"])
        self.assertFalse(self.facts(mv, [], "B", [rec])[3]["broken"])
        # the checker's own "recorded" note is not read: an event saying so changes nothing
        note = [("recorded", 3, None, None, None, "h1", {"seq": 0})]
        self.assertTrue(self.facts(note + mv, [], "B", [])[3]["broken"])
        # a changed entry, in either record
        self.assertTrue(self.facts(mv, [dict(line, to="debug_bucket")], "A")[3]["broken"])
        self.assertTrue(self.facts(mv, [], "B", [dict(rec, handover=dict(rec["handover"], item_ids=["x"]))])[3]["broken"])
        # an own log that is wrong does not matter under B, and a journal that is wrong does not matter under A
        self.assertFalse(self.facts(mv, [], "B", [rec])[3]["broken"])
        self.assertFalse(self.facts(mv, [line], "A", [])[3]["broken"])


class TextRules(unittest.TestCase):
    V = {"expert_certainty": "low", "given_answer": None, "given_by": None,
         "evidence": [{"source_id": "pmid:1"}]}

    def test_verdicts(self):
        tv = lambda r, t, j=None: score.text_verdict(r, t, self.V, D, j)
        self.assertEqual(tv(4, GOOD), "kept")
        self.assertEqual(tv(4, GOOD.replace("pmid:1", "pmid:9")), "broken")
        self.assertEqual(tv(4, "Claim: may help"), "broken")
        self.assertEqual(tv(4, "Claim: may help", "kept"), "kept")
        self.assertEqual(tv(5, GOOD), "kept")
        self.assertEqual(tv(5, GOOD.replace("may", "")), "broken")
        self.assertEqual(tv(5, "no claim here"), "undecided")
        self.assertEqual(tv(6, NOMARK), "broken")

    def test_clean_stored_answer_has_no_rule_5(self):
        v = {"expert_certainty": None, "given_answer": "a", "given_by": "openevidence", "evidence": []}
        self.assertEqual(score.text_verdict(5, "Claim: x [source: tool:openevidence]", v, D, None), "na")
        self.assertEqual(score.text_verdict(4, "Claim: x [source: tool:openevidence]\n[AI-generated]", v, D, None), "kept")


class Call(unittest.TestCase):
    def test_call(self):
        up = lambda k, n: stats.upper_bound(k, n)
        self.assertEqual(score.call_for(35, up(0, 35), 0.0, D), "no call")
        self.assertEqual(score.call_for(36, up(0, 36), 0.0, D), "enough")
        self.assertEqual(score.call_for(100, up(5, 100), 0.0, D), "not enough")
        self.assertEqual(score.call_for(100, up(4, 100), 0.05, D), "not enough")
        self.assertEqual(score.call_for(100, up(4, 100), 0.04, D), "enough")


class HandMade(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        s = Store(cls.tmp.name)
        mv = lambda: send(3, "analytics", "h1")
        # v1 and v2: planted rule 1 violations (test cases)
        s.visit("v1", "c1", "test", fault=F1)
        s.run("v1", "c1", "test", "A", events=mv())                                            # missed
        s.run("v1", "c1", "test", "A+", events=mv(),
              signals=[(1, "flag", "watcher", 3, {"handover_id": "h1", "item_ids": ["i1"]})])  # flagged: names the handover
        s.run("v1", "c1", "test", "B", events=ASKED_ONLY, signals=[(1, "block", "gate", 3)])   # blocked: stopped
        s.visit("v2", "c1", "test", fault=F1)
        s.run("v2", "c1", "test", "A", events=mv(), signals=[(1, "flag", "review", 9)])        # flagged, rule only: unpaired
        # v3: a practice case, missed under A
        s.visit("v3", "c2", "tune", fault=F1)
        s.run("v3", "c2", "tune", "A", events=mv())
        # v8: a planted violation that did not take effect
        s.visit("v8", "c7", "test", fault=F1)
        s.run("v8", "c7", "test", "A", events=send(3, "note_writer", "h1"), own_log=[log_line("h1")])
        # v4: clean with a false alarm; v5: clean and quiet
        s.visit("v4", "c3", "test")
        s.run("v4", "c3", "test", "A", signals=[(1, "flag", "review", 9)])
        s.visit("v5", "c4", "test")
        s.run("v5", "c4", "test", "A")
        # v6: rule 6 planted, flagged; v7: a natural rule 6 violation, missed
        s.visit("v6", "c5", "test", fault=F6)
        s.run("v6", "c5", "test", "A", texts=[("patient_note", NOMARK)], signals=[(6, "flag", "review", 25, {"item_ids": ["v6.A.r0-patient_note"]})])
        s.visit("v7", "c6", "test")
        s.run("v7", "c6", "test", "A", texts=[("patient_note", NOMARK)])
        s.auto_judge()
        s.write()
        cls.res = score.score_run(cls.tmp.name, W, D)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def outcomes(self, rule, cond, natural=False):
        return {a["visit_id"]: a["outcome"] for a in self.res["attempts"]
                if a["rule"] == rule and a["condition"] == cond and a["natural"] == natural}

    def test_outcomes(self):
        self.assertEqual(self.outcomes(1, "A"), {"v1": "missed", "v2": "flag not comparable", "v3": "missed", "v8": "did_not_fire"})
        self.assertEqual(self.outcomes(1, "A+"), {"v1": "flagged"})
        self.assertEqual(self.outcomes(1, "B"), {"v1": "blocked"})
        self.assertEqual(self.outcomes(6, "A"), {"v6": "flagged"})
        self.assertEqual(self.outcomes(6, "A", natural=True), {"v7": "missed"})
        self.assertEqual(self.res["did_not_fire"], [{"fault_id": "F1", "visit_id": "v8", "rule": 1}])

    def test_attempt_keys(self):
        keys = {"run_id", "visit_id", "conversation_id", "condition", "method", "split", "group", "rule", "fault_id",
                "kind", "part", "natural", "outcome", "break_t", "signal_t", "flag_part", "unpaired", "paired"}
        self.assertTrue(all(set(a) == keys for a in self.res["attempts"]))

    def test_table_rule_1_a(self):
        c = self.res["table"]["1"]["A"]
        # v1 missed, v2 flagged; the practice case v3 is not counted; v8 did not take effect
        # v1 missed; v2's flag names only a rule and there is no clean run of the case: not comparable, in no count
        self.assertEqual((c["violations"], c["missed"], c["flagged"], c["blocked"]), (1, 1, 0, 0))
        self.assertEqual((c["flag_not_comparable"], c["did_not_take_effect"]), (1, 1))
        self.assertAlmostEqual(c["upper"], stats.upper_bound(1, 1))
        self.assertEqual((c["clean_units"], c["false_alarms"]), (3, 1))  # v4 (an alarm), v5 and v7 are the clean cases
        self.assertEqual(c["grade"], "inconclusive")
        self.assertEqual(self.res["unpaired_rows"], 1)

    def test_table_other_cells(self):
        b = self.res["table"]["1"]["B"]
        self.assertEqual((b["violations"], b["missed"], b["blocked"]), (1, 0, 1))
        ap = self.res["table"]["1"]["A+"]
        self.assertEqual((ap["violations"], ap["missed"], ap["flagged"]), (1, 0, 1))
        r6 = self.res["table"]["6"]["A"]
        self.assertEqual((r6["violations"], r6["missed"], r6["flagged"]), (1, 0, 1))
        self.assertEqual(r6["clean_units"], 2)  # v4 and v5 are clean and keep rule 6
        self.assertEqual(self.res["table"]["2"]["A"]["violations"], 0)

    def test_practice_is_a_table_of_its_own(self):
        p = self.res["practice"]
        self.assertEqual(p["label"], "practice set: never counted")
        t = p["table"]["1"]["A"]
        self.assertEqual((t["violations"], t["missed"]), (1, 1))
        self.assertEqual(p["table"]["6"]["A"]["violations"], 0)

    def test_output_kept_and_files(self):
        self.assertEqual(self.res["output_kept"]["A"], 1.0)
        self.assertEqual(self.res["output_kept"]["B"], 1.0)
        self.assertNotIn("C", self.res["output_kept"])  # a fourth condition is not scored
        # every advice text is judged here, so this is a complete scoring
        self.assertTrue((Path(self.tmp.name) / "scores.json").exists())
        self.assertFalse((Path(self.tmp.name) / "scores.partial.json").exists())


if __name__ == "__main__":
    unittest.main()
