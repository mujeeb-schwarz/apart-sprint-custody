"""Acceptance tests for BENCH: the world, the fault plan, one run, all runs and the store.

Written from docs/FRAME.md section 9, config/design_choices.json (D: faults, procedures,
store, exports) and the frame addendum. The parts the bench drives (engine, courier,
ledger, review, receipt builder, prove) are small fakes written here; only
custody/core.py and the public signatures of D: exports are imported. A test fails with
a clear message when the part is missing; none is skipped.
"""
import copy
import dataclasses
import importlib
import json
import sys
import tempfile
import unittest
from dataclasses import asdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from custody import core
from custody.core import (ContractError, Handover, Item, Record, RunResult, StepContext, StepOutput, TruthEvent, Visit,
                          canon, claim_level, fingerprint, has_ai_mark, make_item_id, sources_named)

D = json.loads((ROOT / "config" / "design_choices.json").read_text(encoding="utf-8"))
W = json.loads((ROOT / "wiring" / "wiring.json").read_text(encoding="utf-8"))
DEV = {f["fault_id"]: f for f in D["faults"]["development"]}
EVERY = D["prompts"]["fields"]["every_prompt"]
NOT_RUN = {"status": "not_run", "proven_rules": [], "counterexample": None, "states": None}
CONV = "[doctor] How are you?\n[patient] My knee hurts."
MARK = D["markers"]["ai"]
LOG_KEYS = {"run_id", "t", "step", "action", "kind", "from", "to", "item_ids", "move_id", "handover_id"}


def need(modname, *attrs):
    try:
        mod = importlib.import_module(modname)
    except Exception as e:
        raise AssertionError("part missing or broken: cannot import %s (%s: %s)" % (modname, type(e).__name__, e))
    out = []
    for a in attrs:
        if not hasattr(mod, a):
            raise AssertionError("part wrong: %s has no attribute %s" % (modname, a))
        out.append(getattr(mod, a))
    return out[0] if len(out) == 1 else tuple(out)


def read_jsonl(path):
    p = Path(path)
    if not p.exists():
        return []
    return [json.loads(ln) for ln in p.read_text(encoding="utf-8").splitlines() if ln.strip()]


def bvisit(i, split="test", grade="low", stored=False):
    return Visit("v%04d" % i, "aci:C%d" % i, CONV, ("pocqi:%d" if stored else "medev:%d") % i, "Does X reduce Y?",
                 [] if stored else [{"source_id": "pmid:1", "title": "Trial", "text": "Evidence."}],
                 "EXPERT-ANSWER-%d" % i, None if stored else grade, "A stored answer." if stored else None,
                 "openevidence" if stored else None, split, True, {"subset": "aci", "file": "train.csv"})


# ------------------------------------------------------------------ fake parts

class FakeLedger:
    def __init__(self, run_dir, run_id):
        self.run_dir = Path(run_dir)
        self.run_id = run_id
        self.recs = []
        self.jpath = self.run_dir / "journal" / ("%s.jsonl" % run_id)
        self.wpath = self.run_dir / "witness" / "log.jsonl"

    def write(self, rec):
        self.jpath.parent.mkdir(parents=True, exist_ok=True)
        self.wpath.parent.mkdir(parents=True, exist_ok=True)
        prev = self.recs[-1].fp if self.recs else ""
        body = {k: v for k, v in asdict(rec).items() if k not in ("fp", "receipt")}
        body["seq"] = len(self.recs)
        body["prev_fp"] = prev
        fp = fingerprint(body)
        out = dataclasses.replace(rec, seq=len(self.recs), prev_fp=prev, fp=fp)
        line = asdict(out)
        line["receipt"] = None
        with open(self.jpath, "a", encoding="utf-8") as f:
            f.write(canon(line) + "\n")
        n = len(read_jsonl(self.wpath))
        entry = {"index": n, "record_fp": fp, "prev_head": "0" * 64, "head": fingerprint(fp), "t": rec.t, "mac": "m"}
        with open(self.wpath, "a", encoding="utf-8") as f:
            f.write(canon(entry) + "\n")
        out = dataclasses.replace(out, receipt=entry)
        self.recs.append(out)
        return out

    def records(self):
        return list(self.recs)


class FakeCourier:
    def __init__(self, deliver, ledger, run_id):
        self.deliver = deliver
        self.ledger = ledger
        self.run_id = run_id
        self.signals = []

    def admit(self, item, place, t, facts):
        pass

    def made(self, item, place, t, step, parents):
        pass

    def send(self, h, items):
        if self.ledger is not None:
            self.ledger.write(Record(0, h.run_id, h.t, asdict(h), [], [], "deliver", "", "", None))
        self.deliver(h, items)
        return True

    def close(self, t):
        if self.ledger is not None:
            self.ledger.write(Record(0, self.run_id, t, {"action": "close", "t": t}, [], [], "deliver", "", "", None))


class Rec:
    """What the fake parts were handed."""

    def __init__(self):
        self.engine, self.courier, self.review, self.ledger, self.receipt, self.check, self.prove = [], [], [], [], [], [], []
        self.crash_left = {}


PLAN_T = "PLAN\nClaim: The treatment may reduce the outcome. [source: pmid:1]\n" + MARK


def make_parts(rec, prove=None):
    def step_transcriber(ctx, inbox):
        return StepOutput([], [], [])  # version 2: a program step that holds the transcript and makes nothing

    def step_plan(ctx, inbox):
        it = Item(make_item_id(ctx.visit.visit_id, "plan", "plan", PLAN_T), ctx.visit.visit_id, "plan", PLAN_T, "plan",
                  [i.item_id for i in inbox])
        return StepOutput([it], [], [])

    def step_patient_note(ctx, inbox):
        claim = [ln for ln in inbox[0].text.splitlines() if ln.startswith("Claim:")][0]
        text = "FOR YOU\n%s\n%s" % (claim, MARK)
        it = Item(make_item_id(ctx.visit.visit_id, "patient_note", "patient_note", text), ctx.visit.visit_id,
                  "patient_note", text, "patient_note", [i.item_id for i in inbox])
        return StepOutput([it], [], [])

    def step_janitor(ctx, inbox):
        return StepOutput([], [], [i.item_id for i in inbox])

    steps = {"transcriber": step_transcriber, "plan": step_plan, "patient_note": step_patient_note,
             "janitor": step_janitor}

    def recording_ai(inner, sink):
        def f(pid, fields):
            out = inner(pid, fields)
            sink.append({"call_id": fingerprint([pid, fields]), "prompt_id": pid, "fields": dict(fields), "output": out})
            return out
        return f

    def make_courier(condition, wiring, choices, deliver, ledger, ai, run_id):
        rec.courier.append({"condition": condition, "wiring": copy.deepcopy(wiring), "choices": copy.deepcopy(choices),
                            "run_id": run_id, "has_ledger": ledger is not None})
        return FakeCourier(deliver, ledger, run_id)

    def make_ledger(run_dir, run_id, choices):
        rec.ledger.append(copy.deepcopy(choices))
        return FakeLedger(run_dir, run_id)

    def review(own_log, final, wiring, choices, ai, run_id):
        rec.review.append({"own_log": copy.deepcopy(own_log), "final": copy.deepcopy(final), "choices": copy.deepcopy(choices),
                           "wiring": copy.deepcopy(wiring)})
        return []

    def build_receipt(run_id, condition, records, proof, wiring, choices):
        rec.receipt.append({"choices": copy.deepcopy(choices), "records": copy.deepcopy(records)})
        return {"run_id": run_id, "condition": condition, "records": records, "proof": proof}

    def check_receipt(receipt, records, entries, key=None):
        rec.check.append({"records": copy.deepcopy(records), "entries": copy.deepcopy(entries)})
        problems = []
        prev = ""
        for i, r in enumerate(records):
            body = {k: v for k, v in r.items() if k not in ("fp", "receipt")}
            if fingerprint(body) != r.get("fp") or r.get("prev_fp") != prev:
                problems.append("record %d does not match its fingerprint" % i)
            prev = r.get("fp")
        return {"ok": not problems, "problems": problems}

    def prove_(wiring):
        rec.prove.append(copy.deepcopy(wiring))
        return copy.deepcopy(prove) if prove is not None else dict(NOT_RUN)

    def run_visit(visit, wiring, steps_, ai, courier, world, events, choices, run_id):
        rec.engine.append({"visit": visit, "wiring": copy.deepcopy(wiring), "choices": copy.deepcopy(choices),
                           "events": copy.deepcopy(list(events)), "run_id": run_id})
        if rec.crash_left.get(run_id, 0) > 0:
            rec.crash_left[run_id] -= 1
            raise RuntimeError("the fake engine crashes on purpose")
        n = [0]
        log = []

        def mk_item(kind, text, made_by, parents=()):
            return Item(make_item_id(visit.visit_id, kind, made_by, text), visit.visit_id, kind, text, made_by,
                        [p.item_id for p in parents])

        def ho(action, step, frm, to, kind, items, move_id, logged=True):
            n[0] += 1
            t = world.tick()
            h = Handover("%s#%d" % (run_id, n[0]), run_id, t, action, step, frm, to, kind, [i.item_id for i in items], move_id)
            world.asked(h, items)
            courier.send(h, items)
            if logged:
                log.append({"run_id": run_id, "t": t, "step": step, "action": action, "kind": kind, "from": frm, "to": to,
                            "item_ids": h.item_ids, "move_id": move_id, "handover_id": h.handover_id})

        def ctx(sid, place, duty=None):
            return StepContext(visit, sid, place, world.now(), ai, {}, choices, duty)

        def duties(names):
            for duty, place, kind in (("d3", "transcriber", "transcript"), ("d4", "note_writer", "transcript")):
                items = [i for i in world.copies(place) if i.kind == kind]
                if not items:
                    continue
                o = steps_["janitor"](ctx("janitor", place, names(duty)), items)
                ids = set(o.deletes)
                dels = [i for i in items if i.item_id in ids]
                if dels:
                    ho("delete", "janitor", place, None, kind, dels, duty)

        aud = mk_item("transcript", visit.conversation, "intake")
        qst = mk_item("question", visit.question, "intake")
        world.put("transcriber", aud, "intake")
        world.put("clinician", qst, "intake")
        courier.admit(aud, "transcriber", 0, {"source": [visit.conversation_id], "certainty": None, "ai_made": False})
        for e in events:
            world.note("event", {"on": e["on"], "at": e["at"], "detour": "r?"})
        ai(D["prompts"]["note_writer"], dict({"transcript": aud.text}, claim_marker=D["markers"]["claim"],
                                              source_open=D["markers"]["source_tag"]["open"], ai_mark=MARK))
        world.tick()
        out = steps_["transcriber"](ctx("transcriber", "transcriber"), [aud])
        for it in out.items:
            world.put("transcriber", it, "transcriber")
        for rq in out.requests:
            items = [i for i in world.copies("transcriber") if i.kind == rq["kind"]]
            if rq["op"] == "send" and items:
                ho("send", "transcriber", "transcriber", rq["to"], rq["kind"], items, None, logged=rq.get("logged", True))
            elif rq["op"] == "keep":
                for i in items:
                    world.keep("transcriber", mk_item(i.kind, i.text, "keep:transcriber"))
        ho("send", "transcriber", "transcriber", "note_writer", "transcript",
           [i for i in world.copies("transcriber") if i.kind == "transcript"], "w2")
        duties(lambda d: d)
        world.tick()
        po = steps_["plan"](ctx("plan", "clinician"), [qst])
        for it in po.items:
            world.put("clinician", it, "plan")
        ho("send", "plan", "clinician", "summary_writer", "plan", po.items, "a3")
        no = steps_["patient_note"](ctx("patient_note", "summary_writer"), po.items)
        for it in no.items:
            world.put("summary_writer", it, "patient_note")
        ho("send", "patient_note", "summary_writer", "patient", "patient_note", no.items, "a4")
        world.tick()
        world.advance(11)
        duties(lambda d: "late:" + d)
        courier.close(world.now())
        pn = [i for i in world.copies("patient") if i.kind == "patient_note"]
        return {"own_log": log, "final": {"note": None, "patient_note": pn[0].text if pn else None}, "skipped": []}

    return {"steps": steps, "ai": lambda pid, fields: "AI", "recording_ai": recording_ai, "run_visit": run_visit,
            "make_courier": make_courier, "review": review, "make_ledger": make_ledger, "build_receipt": build_receipt,
            "check_receipt": check_receipt, "prove": prove_}


class Go:
    """One run with fake parts into a fresh temporary folder."""

    def __init__(self, fault, cond, visit=None, prove=None, rec=None, wiring=None, rep=0):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name) / "run"
        self.dir.mkdir()
        self.rec = rec or Rec()
        self.parts = make_parts(self.rec, prove)
        self.visit = visit or bvisit(1)
        self.choices = copy.deepcopy(D)  # still holds the key faults; the bench must strip it
        self.wiring = wiring if wiring is not None else copy.deepcopy(W)
        run_one = need("custody.bench", "run_one")
        self.res = run_one(self.visit, cond, fault, self.parts, self.wiring, self.choices, self.dir, rep)
        self.cond = cond

    def close(self):
        self.tmp.cleanup()

    def f(self, rel):
        return read_jsonl(self.dir / rel)

    @property
    def truth(self):
        return self.f("hidden/truth.jsonl")

    @property
    def run_id(self):
        return "%s.%s.r0" % (self.visit.visit_id, self.cond)


def assert_refused(test, fault, promise_tolerated=False):
    plan_faults, run_one = need("custody.faults", "plan_faults"), need("custody.bench", "run_one")
    vs = [bvisit(1, "tune"), bvisit(2, "test")]
    try:
        plan = plan_faults(vs, [fault], copy.deepcopy(D))
    except ContractError:
        return
    v = next((v for v in vs if plan.get(v.visit_id)), None)
    test.assertIsNotNone(v, "fault %s was planned onto no visit and not refused" % fault["fault_id"])
    rec = Rec()
    with tempfile.TemporaryDirectory() as d:
        try:
            run_one(v, "B", plan[v.visit_id], make_parts(rec), copy.deepcopy(W), copy.deepcopy(D), Path(d), 0)
        except ContractError:
            return
    if promise_tolerated and rec.engine:
        test.assertEqual(rec.engine[0]["wiring"]["promise"], W["promise"], "the promise must never change")
        return
    test.fail("fault %s was refused neither when planned nor when run" % fault["fault_id"])


# ------------------------------------------------------------------ the world

class TestWorld(unittest.TestCase):
    def setUp(self):
        self.World = need("custody.world", "World")
        self.w = self.World("v0001.B.r0", copy.deepcopy(W), copy.deepcopy(D))

    def item(self, kind="audio", text="a"):
        return Item(make_item_id("v0001", kind, "x", text), "v0001", kind, text, "x", [])

    def h(self, action, frm, to, kind, items, t=1):
        return Handover("v0001.B.r0#1", "v0001.B.r0", t, action, "s", frm, to, kind, [i.item_id for i in items], None)

    def test_clock(self):
        self.assertEqual(self.w.now(), 0)
        self.assertEqual(self.w.tick(), 1)
        self.assertEqual(self.w.advance(3), 4)
        self.assertEqual(self.w.now(), 4)

    def test_put_and_copies_in_arrival_order_one_copy_at_most(self):
        a, b = self.item(text="a"), self.item(text="b")
        self.w.put("recorder", a, "intake")
        self.w.put("recorder", b, "intake")
        self.assertEqual([i.item_id for i in self.w.copies("recorder")], [a.item_id, b.item_id])
        self.w.put("recorder", a, "intake")
        self.assertEqual(len(self.w.copies("recorder")), 2, "a second arrival of an item changes nothing")

    def test_deliver_send_keeps_the_senders_copy_and_delete_removes_it(self):
        a = self.item()
        self.w.put("recorder", a, "intake")
        self.w.asked(self.h("send", "recorder", "transcriber", "audio", [a]), [a])
        self.assertEqual(self.w.copies("transcriber"), [], "asking moves nothing")
        self.w.deliver(self.h("send", "recorder", "transcriber", "audio", [a]), [a])
        self.assertEqual([i.item_id for i in self.w.copies("transcriber")], [a.item_id])
        self.assertEqual([i.item_id for i in self.w.copies("recorder")], [a.item_id], "the sender keeps its copy")
        self.w.deliver(self.h("delete", "recorder", None, "audio", [a], 2), [a])
        self.assertEqual(self.w.copies("recorder"), [])

    def test_a_kept_copy_is_never_returned_moved_or_deleted(self):
        a = self.item()
        self.w.keep("transcriber", a)
        self.assertEqual(self.w.copies("transcriber"), [])
        self.w.deliver(self.h("delete", "transcriber", None, "audio", [a]), [a])  # must not raise
        self.assertEqual(self.w.copies("transcriber"), [])

    def test_a_place_missing_from_the_wiring_raises_nothing(self):
        a = self.item()
        self.w.put("nowhere_at_all", a, "intake")
        self.assertEqual([i.item_id for i in self.w.copies("nowhere_at_all")], [a.item_id])
        self.w.deliver(self.h("send", "nowhere_at_all", "also_missing", "audio", [a]), [a])
        self.assertEqual(len(self.w.copies("also_missing")), 1)
        self.assertEqual(self.w.copies("never_used"), [])


# ------------------------------------------------------------------ run_choices

class TestRunChoices(unittest.TestCase):
    def test_a_copy_without_the_key_faults(self):
        run_choices = need("custody.bench", "run_choices")
        full = copy.deepcopy(D)
        out = run_choices(full)
        self.assertNotIn("faults", out)
        self.assertIn("faults", full, "the original is not changed")
        self.assertEqual({k: v for k, v in full.items() if k != "faults"}, out)
        out["markers"]["claim"] = "changed"
        self.assertEqual(full["markers"]["claim"], D["markers"]["claim"], "a copy, not a view")


# ------------------------------------------------------------------ the plan

def e2e_visits():
    return [bvisit(i, "tune") for i in range(1, 9)] + [bvisit(i, "test") for i in range(51, 59)]


class TestPlanFaults(unittest.TestCase):
    def setUp(self):
        self.plan_faults = need("custody.faults", "plan_faults")
        self.dev = copy.deepcopy(D["faults"]["development"])

    def fid(self, plan):
        return {v: (f["fault_id"] if f else None) for v, f in plan.items()}

    def test_the_twelve_development_faults_land_where_the_frame_says(self):
        plan = self.plan_faults(e2e_visits(), self.dev, copy.deepcopy(D))
        want = {"v0001": "F1", "v0002": "F2", "v0003": "F3", "v0051": "F4", "v0052": "F5", "v0053": "F6",
                "v0004": "F7", "v0005": "F8", "v0006": "F9", "v0054": "F10", "v0007": "F11", "v0008": "F12",
                "v0055": None, "v0056": None, "v0057": None, "v0058": None}
        self.assertEqual(self.fid(plan), want)

    def test_the_plan_comes_out_the_same_twice(self):
        a = self.plan_faults(e2e_visits(), copy.deepcopy(self.dev), copy.deepcopy(D))
        b = self.plan_faults(e2e_visits(), copy.deepcopy(self.dev), copy.deepcopy(D))
        self.assertEqual(json.dumps(a, sort_keys=True), json.dumps(b, sort_keys=True))

    def many(self):
        vs = []
        for i in range(1, 41):
            split = "tune" if i <= 12 else "test"
            stored = i % 5 == 0
            grade = ["high", "moderate", "low", "very low"][i % 4]
            vs.append(bvisit(i, split, grade, stored))
        return vs

    def test_a_larger_set_is_shuffled_with_the_seed_and_still_the_same_twice(self):
        vs = self.many()
        a = self.plan_faults(vs, copy.deepcopy(self.dev), copy.deepcopy(D))
        b = self.plan_faults(copy.deepcopy(vs), copy.deepcopy(self.dev), copy.deepcopy(D))
        self.assertEqual(json.dumps(a, sort_keys=True), json.dumps(b, sort_keys=True))
        placed = [f["fault_id"] for f in a.values() if f]
        self.assertEqual(sorted(placed), sorted(f["fault_id"] for f in self.dev), "each fault goes to exactly one visit")
        self.assertEqual(set(a), {v.visit_id for v in vs}, "every visit is in the plan, faulted or clean")

    def test_planning_respects_needs_and_the_test_visit_rule(self):
        vs = self.many()
        byid = {v.visit_id: v for v in vs}
        plan = self.plan_faults(vs, copy.deepcopy(self.dev), copy.deepcopy(D))
        for vid, f in plan.items():
            if not f:
                continue
            v = byid[vid]
            if f["rule"] in (4, 5, 6) or any(o["op"] == "inject" for o in f["ops"]):
                self.assertEqual(v.split, "test", "%s must go to a test visit" % f["fault_id"])
            needs = f.get("needs", {})
            if "expert_certainty_in" in needs:
                self.assertIn(v.expert_certainty, needs["expert_certainty_in"])
        extra = [{"fault_id": "N1", "kind": "step", "rule": 6, "says": "s", "ops": [{"op": "rewrite", "step": "patient_note",
                                                                                  "mode": "drop_ai_mark"}],
                  "patch": [], "events": [], "needs": {"stored_answer": True}},
                 {"fault_id": "N2", "kind": "step", "rule": 6, "says": "s", "ops": [{"op": "rewrite", "step": "patient_note",
                                                                                  "mode": "drop_ai_mark"}],
                  "patch": [], "events": [], "needs": {"stored_answer": False, "expert_certainty_in": ["high"]}}]
        plan = self.plan_faults(vs, extra, copy.deepcopy(D))
        for vid, f in plan.items():
            if f and f["fault_id"] == "N1":
                self.assertIsNotNone(byid[vid].given_answer, "stored_answer true needs a stored answer")
            if f and f["fault_id"] == "N2":
                self.assertIsNone(byid[vid].given_answer)
                self.assertEqual(byid[vid].expert_certainty, "high")
        self.assertEqual(sorted(f["fault_id"] for f in plan.values() if f), ["N1", "N2"])

    def test_a_fault_that_no_visit_can_take_is_left_out(self):
        nobody = {"fault_id": "NX", "kind": "step", "rule": 5, "says": "s", "ops": [{"op": "rewrite", "step": "patient_note",
                                                                                   "mode": "set_level", "level": "high"}],
                  "patch": [], "events": [], "needs": {"expert_certainty_in": ["moderate"]}}
        vs = [bvisit(i, "test", "low") for i in range(1, 6)]
        plan = self.plan_faults(vs, [nobody], copy.deepcopy(D))
        self.assertEqual([f for f in plan.values() if f], [])

    def test_an_unknown_needs_key_raises_contract_error(self):
        bad = {"fault_id": "NK", "kind": "step", "rule": 6, "says": "s", "ops": [], "patch": [], "events": [],
               "needs": {"colour": "red"}}
        with self.assertRaises(ContractError):
            self.plan_faults(e2e_visits(), [bad], copy.deepcopy(D))

    def test_faults_that_break_the_format_are_refused(self):
        base = {"fault_id": "BAD", "kind": "wiring", "rule": 1, "says": "s", "ops": [], "patch": [], "events": [], "needs": {}}
        promise = dict(base, patch=[{"op": "replace", "path": "/promise/places/0/named", "value": False}])
        assert_refused(self, promise, promise_tolerated=True)
        outside = dict(base, patch=[{"op": "remove", "path": "/kinds/0"}])
        assert_refused(self, outside)
        step = dict(base, kind="step", ops=[{"op": "extra_send", "step": "no_such_step", "kind": "transcript",
                                             "to": "analytics", "logged": False}])
        assert_refused(self, step)
        duty = dict(base, kind="step", ops=[{"op": "skip_delete", "duty": "d99"}])
        assert_refused(self, duty)


# ------------------------------------------------------------------ one run

class TestRunOneClean(unittest.TestCase):
    def test_a_clean_run_under_each_condition(self):
        for cond in ("A", "A+", "B", "C"):
            g = Go(None, cond)
            try:
                res = g.res
                self.assertIsInstance(res, RunResult)
                self.assertEqual(res.run_id, g.run_id)
                self.assertEqual((res.visit_id, res.conversation_id, res.condition, res.rep, res.split),
                                 ("v0001", "aci:C1", cond, 0, "test"))
                self.assertFalse(res.crashed)
                self.assertTrue(res.produced["patient_note"])
                self.assertGreater(res.asked, 0)
                self.assertEqual(res.delivered, res.asked)
                self.assertEqual(res.signals, 0)
                self.assertEqual(res.ai_calls, 1)
                self.assertEqual(res.proof, "not_run" if cond == "C" else "none")
                self.assertEqual(g.f("signals.jsonl"), [])
                self.assertEqual(len(g.f("ai_calls.jsonl")), 1)
                self.assertEqual(g.f("ai_calls.jsonl")[0]["run_id"], g.run_id)
                self.assertEqual(set(g.f("ai_calls.jsonl")[0]), {"run_id", "call_id", "prompt_id", "fields", "output"})
                if cond in ("B", "C"):
                    self.assertTrue(res.receipt_ok)
                else:
                    self.assertIsNone(res.receipt_ok)
                self.assertTrue((g.dir / "receipts" / ("%s.json" % g.run_id)).exists())
            finally:
                g.close()

    def test_the_stored_files_have_their_fields_and_no_labels(self):
        g = Go(None, "B")
        try:
            for ln in g.f("own_log.jsonl"):
                self.assertEqual(set(ln), LOG_KEYS)
            texts = g.f("texts.jsonl")
            self.assertTrue(texts)
            for row in texts:
                self.assertEqual(set(row), {"run_id", "place", "t", "item"})
            self.assertIn("transcript", [r["item"]["kind"] for r in texts], "intake items are in texts.jsonl")
            raw = (g.dir / "texts.jsonl").read_text(encoding="utf-8")
            self.assertNotIn('"delete_by"', raw, "labels never appear in texts.jsonl")
            self.assertNotIn('"allowed"', raw)
        finally:
            g.close()

    def test_truth_and_plan_sit_under_hidden_only(self):
        g = Go(None, "B")
        try:
            self.assertTrue((g.dir / "hidden" / "truth.jsonl").exists())
            for p in g.dir.rglob("*"):
                if p.name in ("truth.jsonl", "plan.jsonl"):
                    self.assertEqual(p.parent.name, "hidden", "%s must sit under hidden/" % p)
            fields = {f.name for f in dataclasses.fields(TruthEvent)}
            kinds = set(D["store"]["truth_kinds"])
            self.assertTrue(g.truth)
            for ev in g.truth:
                self.assertEqual(set(ev), fields)
                self.assertIn(ev["kind"], kinds)
                self.assertEqual(ev["run_id"], g.run_id)
                self.assertIsNone(ev["fault_id"], "a clean run carries no fault id")
            self.assertEqual([e["seq"] for e in g.truth], list(range(len(g.truth))))
            self.assertIn("made", {e["kind"] for e in g.truth})
            self.assertIn("asked", {e["kind"] for e in g.truth})
            self.assertIn("moved", {e["kind"] for e in g.truth})
        finally:
            g.close()

    def test_each_ledger_write_becomes_a_recorded_truth_event_under_b_and_c_only(self):
        for cond, want in (("A", False), ("A+", False), ("B", True), ("C", True)):
            g = Go(None, cond)
            try:
                rec_ev = [e for e in g.truth if e["kind"] == "recorded"]
                if want:
                    jr = g.f("journal/%s.jsonl" % g.run_id)
                    self.assertTrue(jr)
                    self.assertEqual(len(rec_ev), len(jr))
                    self.assertEqual([e["detail"]["fp"] for e in rec_ev], [r["fp"] for r in jr])
                    self.assertEqual([e["detail"]["seq"] for e in rec_ev], [r["seq"] for r in jr])
                else:
                    self.assertEqual(rec_ev, [])
            finally:
                g.close()


class TestHiddenFromTheMethods(unittest.TestCase):
    def test_every_part_gets_choices_without_the_key_faults(self):
        for cond in ("A", "A+", "B", "C"):
            g = Go(DEV["F1"], cond)
            try:
                r = g.rec
                seen = [e["choices"] for e in r.engine] + [e["choices"] for e in r.courier] + [e["choices"] for e in r.review] \
                    + [e["choices"] for e in r.receipt] + r.ledger
                self.assertTrue(len(seen) >= 4)
                for c in seen:
                    self.assertNotIn("faults", c, "%s: a part was given the fault list" % cond)
                self.assertIn("faults", g.choices, "the bench must work on a copy")
            finally:
                g.close()

    def test_the_engine_gets_a_visit_without_the_hidden_fields(self):
        g = Go(None, "B")
        try:
            v = g.rec.engine[0]["visit"]
            self.assertEqual((v.visit_id, v.conversation, v.question), (g.visit.visit_id, g.visit.conversation, g.visit.question))
            self.assertIsNone(v.expert_answer)
            self.assertEqual((v.split, v.matched, v.meta), ("", False, {}))
            self.assertEqual(v.expert_certainty, g.visit.expert_certainty, "the grade stays for the canned text")
        finally:
            g.close()

    def test_b_and_c_are_given_the_same_courier_arguments_except_condition_and_run_id(self):
        gb, gc = Go(None, "B"), Go(None, "C")
        try:
            b, c = gb.rec.courier[0], gc.rec.courier[0]
            self.assertEqual((b["condition"], c["condition"]), ("B", "C"))
            self.assertEqual(b["wiring"], c["wiring"])
            self.assertEqual(b["choices"], c["choices"])
            self.assertEqual(b["has_ledger"], c["has_ledger"])
            self.assertTrue(b["has_ledger"])
        finally:
            gb.close()
            gc.close()

    def test_no_ledger_under_a_and_a_plus(self):
        for cond in ("A", "A+"):
            g = Go(None, cond)
            try:
                self.assertFalse(g.rec.courier[0]["has_ledger"])
                self.assertEqual(g.rec.ledger, [])
                self.assertFalse((g.dir / "journal" / ("%s.jsonl" % g.run_id)).exists())
            finally:
                g.close()


class TestWiringFaultsAndProof(unittest.TestCase):
    def test_a_wiring_patch_reaches_the_engine_and_the_original_is_untouched(self):
        orig = copy.deepcopy(W)
        wiring = copy.deepcopy(W)
        g = Go(DEV["F2"], "A", wiring=wiring)
        try:
            seen = g.rec.engine[0]
            self.assertEqual(len(seen["wiring"]["plumbing"]["detours"][0]["do"]), 2, "F2 removes the last step of r1")
            self.assertEqual(seen["events"], [{"on": "timeout", "at": "w3"}])
            self.assertEqual(seen["wiring"]["promise"], orig["promise"])
            self.assertEqual(wiring, orig, "the bench patches a copy")
        finally:
            g.close()
        g = Go(DEV["F3"], "A")
        try:
            moves = {m["id"]: m for m in g.rec.engine[0]["wiring"]["plumbing"]["moves"]}
            self.assertFalse(moves["w3"]["via_gate"])
            self.assertTrue(moves["w2"]["via_gate"])
        finally:
            g.close()

    def test_under_c_prove_runs_on_the_patched_wiring_and_only_under_c(self):
        for cond in ("A", "A+", "B"):
            g = Go(DEV["F2"], cond)
            try:
                self.assertEqual(g.rec.prove, [], "prove is asked under C only")
                self.assertEqual(g.res.proof, "none")
            finally:
                g.close()
        passed = {"status": "passed", "proven_rules": [1, 2, 3], "counterexample": None, "states": 40}
        g = Go(DEV["F2"], "C", prove=passed)
        try:
            self.assertEqual(len(g.rec.prove), 1)
            self.assertEqual(len(g.rec.prove[0]["plumbing"]["detours"][0]["do"]), 2)
            self.assertEqual(g.res.proof, "passed")
            self.assertEqual(g.res.signals, 0)
            self.assertEqual(len(g.rec.engine[0]["wiring"]["plumbing"]["detours"][0]["do"]), 2)
        finally:
            g.close()

    def test_a_counterexample_adds_the_proof_signal_and_runs_the_unpatched_wiring(self):
        bad = {"status": "counterexample", "proven_rules": [], "counterexample": {"rule": 2, "property": "P2", "trace": []},
               "states": 40}
        g = Go(DEV["F2"], "C", prove=bad)
        try:
            self.assertEqual(g.res.proof, "counterexample")
            self.assertEqual(len(g.rec.engine[0]["wiring"]["plumbing"]["detours"][0]["do"]), 3, "the faulted wiring never runs")
            sigs = g.f("signals.jsonl")
            proof = [s for s in sigs if s["by"] == "proof"]
            self.assertEqual(len(proof), 1)
            self.assertEqual((proof[0]["level"], proof[0]["t"], proof[0]["rule"], proof[0]["run_id"]), ("block", -1, 2, g.run_id))
            self.assertEqual(g.res.signals, len(sigs))
        finally:
            g.close()

    def test_a_patch_to_the_promise_is_refused(self):
        fault = dict(DEV["F3"], fault_id="FP", patch=[{"op": "replace", "path": "/promise/places/0/named", "value": False}])
        assert_refused(self, fault, promise_tolerated=True)


class TestStepFaultsLeaveTruth(unittest.TestCase):
    def check(self, fid, cond="B"):
        g = Go(DEV[fid], cond)
        self.addCleanup(g.close)
        tagged = [e for e in g.truth if e["fault_id"] == fid]
        self.assertTrue(tagged, "%s left no truth event with its fault_id" % fid)
        self.assertTrue(all(e["run_id"] == g.run_id for e in tagged))
        return g, tagged

    def test_f1_extra_send_unlogged(self):
        g, tagged = self.check("F1")
        self.assertTrue([e for e in g.truth if e["to_place"] == "analytics"], "truth shows the send to analytics")
        self.assertEqual([ln for ln in g.f("own_log.jsonl") if ln["to"] == "analytics"], [], "logged false: no log line")

    def test_f4_wrong_source(self):
        g, _ = self.check("F4")
        plan = [r["item"] for r in g.f("texts.jsonl") if r["item"]["kind"] == "plan"][0]
        self.assertEqual(sources_named(plan["text"], D), [D["faults"]["wrong_source_id"]])

    def test_f5_set_level_keeps_tag_and_mark(self):
        g, _ = self.check("F5")
        pn = [r["item"] for r in g.f("texts.jsonl") if r["item"]["kind"] == "patient_note"][0]["text"]
        self.assertEqual(claim_level(pn, D), "high")
        self.assertEqual(sources_named(pn, D), ["pmid:1"], "the source tag stays on the line")
        self.assertTrue(has_ai_mark(pn, D))

    def test_f6_drop_ai_mark(self):
        g, _ = self.check("F6")
        pn = [r["item"] for r in g.f("texts.jsonl") if r["item"]["kind"] == "patient_note"][0]["text"]
        self.assertFalse(has_ai_mark(pn, D))
        self.assertEqual(sources_named(pn, D), ["pmid:1"])
        self.assertEqual(claim_level(pn, D), "low")

    def test_f7_keep_copy(self):
        g, tagged = self.check("F7")
        self.assertIn("kept", {e["kind"] for e in g.truth})
        kept = [e for e in g.truth if e["kind"] == "kept"][0]
        self.assertEqual((kept["place"], kept["detail"].get("kind")), ("transcriber", "transcript"))

    def test_f8_skip_delete_and_f9_late_delete(self):
        g, _ = self.check("F8")
        self.assertEqual([ln for ln in g.f("own_log.jsonl") if ln["move_id"] == "d3"], [], "the delete is never carried out")
        g9, _ = self.check("F9")
        lines = g9.f("own_log.jsonl")
        d4 = [ln for ln in lines if ln["move_id"] == "d4"]
        a4 = [ln for ln in lines if ln["move_id"] == "a4"][0]
        self.assertEqual(len(d4), 1)
        self.assertGreater(d4[0]["t"], a4["t"], "the delete comes only in the late pass")

    def test_f10_inject_works_on_a_copy_of_the_visit(self):
        g, _ = self.check("F10")
        line = DEV["F10"]["ops"][0]["text"]
        audio = [r["item"] for r in g.f("texts.jsonl") if r["item"]["kind"] == "transcript" and r["item"]["made_by"] == "intake"][0]
        self.assertEqual(audio["text"].splitlines()[-1], line, "the line is the last line of the raw conversation")
        self.assertNotIn(line, g.visit.conversation, "the visit given to the bench is unchanged")

    def test_f11_false_log_drops_the_line_everywhere_and_the_review_sees_it(self):
        for cond in ("A", "B"):
            g, tagged = self.check("F11", cond)
            self.assertEqual([ln for ln in g.f("own_log.jsonl") if ln["step"] == "transcriber" and ln["kind"] == "transcript"], [])
            ed = [e for e in g.truth if e["kind"] == "edited"]
            self.assertTrue(ed and ed[0]["detail"].get("where") == "own_log")
            seen = g.rec.review[0]["own_log"]
            self.assertEqual([ln for ln in seen if ln["step"] == "transcriber" and ln["kind"] == "transcript"], [],
                             "the review reads the log as stored, after the edit")

    def test_f12_edit_record_under_b_edits_the_journal_and_the_receipt_check_notices(self):
        g, tagged = self.check("F12", "B")
        jr = g.f("journal/%s.jsonl" % g.run_id)
        self.assertEqual(jr[0]["t"], 999)
        ed = [e for e in g.truth if e["kind"] == "edited"]
        self.assertEqual(len(ed), 1)
        self.assertEqual((ed[0]["detail"].get("where"), ed[0]["detail"].get("position"), ed[0]["detail"].get("field")),
                         ("journal", 0, "t"))
        # the check ran on the files read back from disk: plain dicts, with the edit in them
        self.assertEqual(g.rec.check[-1]["records"][0]["t"], 999)
        self.assertTrue(all(isinstance(r, dict) for r in g.rec.check[-1]["records"]))
        self.assertFalse(g.res.receipt_ok)
        led = [s for s in g.f("signals.jsonl") if s["by"] == "ledger"]
        self.assertEqual(len(led), 1)
        s = led[0]
        self.assertEqual((s["rule"], s["level"], s["handover_id"], s["item_ids"], s["run_id"]), (3, "flag", None, [], g.run_id))
        self.assertEqual(s["reason"], "record 0 does not match its fingerprint")
        self.assertEqual(s["t"], max(e["t"] for e in g.truth), "the world clock at the end of the run")

    def test_f12_under_a_edits_the_own_log(self):
        g, tagged = self.check("F12", "A")
        self.assertEqual(g.f("own_log.jsonl")[0]["t"], 999)
        ed = [e for e in g.truth if e["kind"] == "edited"]
        self.assertEqual(ed[0]["detail"].get("where"), "own_log")
        self.assertEqual(g.rec.review[0]["own_log"][0]["t"], 999)

    def test_clean_run_has_no_ledger_signal(self):
        g = Go(None, "B")
        try:
            self.assertEqual([s for s in g.f("signals.jsonl") if s["by"] == "ledger"], [])
            self.assertTrue(g.res.receipt_ok)
        finally:
            g.close()


# ------------------------------------------------------------------ all runs and the store

class TestRunAll(unittest.TestCase):
    def setUp(self):
        self.run_all = need("custody.bench", "run_all")
        self.plan_faults = need("custody.faults", "plan_faults")
        self.visits = [bvisit(1, "tune"), bvisit(2, "tune"), bvisit(51), bvisit(52)]
        self.faults = [DEV["F1"], DEV["F3"], DEV["F6"]]

    def go(self, d, rec=None):
        rec = rec or Rec()
        plan = self.plan_faults(self.visits, copy.deepcopy(self.faults), copy.deepcopy(D))
        res = self.run_all(self.visits, ["A", "A+", "B", "C"], plan, make_parts(rec), copy.deepcopy(W), copy.deepcopy(D), Path(d))
        return res, plan, rec

    def test_every_visit_runs_under_every_condition_and_the_store_is_written(self):
        with tempfile.TemporaryDirectory() as d:
            res, plan, rec = self.go(d)
            self.assertEqual(len(res), 16)
            self.assertEqual({r.run_id for r in res},
                             {"%s.%s.r0" % (v.visit_id, c) for v in self.visits for c in ("A", "A+", "B", "C")})
            rows = read_jsonl(Path(d) / "results.jsonl")
            self.assertEqual(len(rows), 16)
            self.assertEqual(set(rows[0]), {f.name for f in dataclasses.fields(RunResult)})
            hp = read_jsonl(Path(d) / "hidden" / "plan.jsonl")
            self.assertEqual({r["visit_id"] for r in hp}, {v.visit_id for v in self.visits})
            self.assertEqual({r["visit_id"]: (r["fault"]["fault_id"] if r["fault"] else None) for r in hp},
                             {v: (f["fault_id"] if f else None) for v, f in plan.items()})
            for p in Path(d).rglob("*"):
                if p.name in ("truth.jsonl", "plan.jsonl"):
                    self.assertEqual(p.parent.name, "hidden")
            self.assertTrue(read_jsonl(Path(d) / "witness" / "log.jsonl"), "B and C runs share one witness log")
            self.assertTrue((Path(d) / "timing.jsonl").exists())

    def test_equal_inputs_give_equal_bytes_timing_aside(self):
        with tempfile.TemporaryDirectory() as d1, tempfile.TemporaryDirectory() as d2:
            self.go(d1)
            self.go(d2)
            files1 = sorted(str(p.relative_to(d1)) for p in Path(d1).rglob("*") if p.is_file() and p.name != "timing.jsonl")
            files2 = sorted(str(p.relative_to(d2)) for p in Path(d2).rglob("*") if p.is_file() and p.name != "timing.jsonl")
            self.assertEqual(files1, files2)
            self.assertTrue(files1)
            for rel in files1:
                self.assertEqual((Path(d1) / rel).read_bytes(), (Path(d2) / rel).read_bytes(), "bytes differ in %s" % rel)

    def test_a_crash_is_retried_once(self):
        rec = Rec()
        rec.crash_left["v0002.B.r0"] = 1
        with tempfile.TemporaryDirectory() as d:
            res, _, _ = self.go(d, rec)
            r = [x for x in res if x.run_id == "v0002.B.r0"][0]
            self.assertFalse(r.crashed, "one crash is retried and the retry succeeds")
            self.assertTrue(r.produced["patient_note"])

    def test_a_second_crash_is_recorded_and_the_other_runs_go_on(self):
        rec = Rec()
        rec.crash_left["v0002.B.r0"] = 5
        with tempfile.TemporaryDirectory() as d:
            res, _, _ = self.go(d, rec)
            self.assertEqual(len(res), 16)
            r = [x for x in res if x.run_id == "v0002.B.r0"][0]
            self.assertTrue(r.crashed)
            self.assertEqual(len([x for x in res if x.crashed]), 1)
            rows = {x["run_id"]: x for x in read_jsonl(Path(d) / "results.jsonl")}
            self.assertTrue(rows["v0002.B.r0"]["crashed"])


class TestWriteManifest(unittest.TestCase):
    def test_manifest_holds_what_it_is_given(self):
        write_manifest = need("custody.store", "write_manifest")
        fps = {"wiring": "a" * 64, "design_choices": "b" * 64, "prompts": {"plan.v1": "c" * 64},
               "data": {"medEvidence.csv": "d" * 64}, "scorer": "e" * 64}
        with tempfile.TemporaryDirectory() as d:
            out = write_manifest(Path(d), "e2e", D["seeds"], ["A", "A+", "B", "C"], {"visits": 16}, fps)
            self.assertIsNone(out)
            m = json.loads((Path(d) / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(m, {"run_name": "e2e", "seeds": D["seeds"], "conditions": ["A", "A+", "B", "C"],
                             "counts": {"visits": 16}, "fingerprints": fps})


if __name__ == "__main__":
    unittest.main()
