"""Tests of the program forger (F1), the validator and the F2 parsing/unmasking. No AI call, no web request.
Written as unittest test cases, which pytest also collects (pytest is not installed on this machine):

    python3 forger/tests/test_forger.py -v      # or, where pytest is installed: python3 -m pytest forger/tests -q
"""
import copy
import json
import sys
from pathlib import Path

import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import lib  # noqa: E402

RID = "c0001+P3-999.A.r0"
T_ITEM, D_ITEM = "aaaa000000000001", "bbbb000000000002"


def line(t, action, frm=None, to=None, kind="transcript", items=(T_ITEM,), n=None, move=None, step="janitor"):
    if action == "intake":
        return {"action": "intake", "item": items[0], "kind": kind, "place": frm, "run_id": RID, "step": "intake", "t": t}
    return {"action": action, "from": frm, "handover_id": "%s#%d" % (RID, n), "item_ids": list(items), "kind": kind,
            "move_id": move, "run_id": RID, "step": step, "t": t, "to": to}


def true_log():
    return [line(0, "intake", "transcriber"),
            line(2, "send", "transcriber", "note_writer", n=1, move="w2", step="transcriber"),
            line(3, "delete", "transcriber", n=2, move="d3"),
            line(5, "send", "note_writer", "record", "note_draft", (D_ITEM,), 3, "w3", "note_writer"),
            line(6, "delete", "note_writer", n=4, move="d4"),
            line(7, "delete", "note_writer", kind="note_draft", items=(D_ITEM,), n=5, move="d5"),
            line(9, "delete", "record", kind="note_draft", items=(D_ITEM,), n=6, move="d6")]


_ENV = []


def get_env():
    if not _ENV:
        choices = lib.datasets.default_choices()
        wiring = lib.assemble.load_wiring()
        _ENV.append((choices, {"promise": wiring["promise"]}))
    return _ENV[0]


FINAL = {"note": "VISIT NOTE\nA short note.", "patient_note": None}


def spec_for(kind, op):
    t = true_log()
    c = copy.deepcopy(t)
    if kind == "entry_removed":
        pos = next(i for i, ln in enumerate(c) if ln["action"] == "send" and ln["step"] == op["step"])
        del c[pos]
    elif kind == "entry_changed":
        pos = next(i for i, ln in enumerate(c) if ln["action"] == "send" and ln["step"] == op["step"])
        (f, v), = op["change"].items()
        c[pos][f] = v
    else:
        a = line(c[op["position"] - 1]["t"], "send", op["from"], op["to"], op["kind"], op["items"], 7, None, op["step"])
        a["move_id"] = None
        c.insert(op["position"], a)
    return t, c, lib.edit_spec(t, c, op, kind)


def nums(log):
    return [int(ln["handover_id"].rsplit("#", 1)[1]) for ln in log if "handover_id" in ln]


PREP = lib.OUT / "prepared.jsonl"


class TestForger(unittest.TestCase):
    def test_removed_w2_drops_the_destination_lines_and_renumbers(self):
        env = get_env()
        t, c, spec = spec_for("entry_removed", {"step": "transcriber", "kind": "transcript", "change": None})
        f = lib.program_forger(c, spec)
        assert not [ln for ln in f if ln["action"] == "send" and ln["from"] == "transcriber"]
        assert not [ln for ln in f if ln.get("from") == "note_writer" and T_ITEM in ln.get("item_ids", [])]  # d4 gone
        assert [ln["move_id"] for ln in f if ln["action"] != "intake"] == ["d3", "w3", "d5", "d6"]
        assert nums(f) == [1, 2, 3, 4]
        assert lib.took_effect(f, spec, FINAL, FINAL, env[1], env[0], RID)["ok"]


    def test_removed_w3_drops_the_record_delete(self):
        env = get_env()
        t, c, spec = spec_for("entry_removed", {"step": "note_writer", "kind": "note_draft", "change": None})
        f = lib.program_forger(c, spec)
        assert [ln["move_id"] for ln in f if ln["action"] != "intake"] == ["w2", "d3", "d4", "d5"]
        assert lib.took_effect(f, spec, FINAL, FINAL, env[1], env[0], RID)["ok"]


    def test_changed_destination_moves_the_destination_delete(self):
        env = get_env()
        op = {"step": "transcriber", "kind": "transcript", "change": {"to": "note_writer_cache"}}
        t, c, spec = spec_for("entry_changed", op)
        f = lib.program_forger(c, spec)
        d4 = next(ln for ln in f if ln.get("move_id") == "d4")
        assert d4["from"] == "note_writer_cache"
        assert next(ln for ln in f if ln.get("move_id") == "w2")["to"] == "note_writer_cache"
        assert lib.took_effect(f, spec, FINAL, FINAL, env[1], env[0], RID)["ok"]


    def test_changed_kind_relabels_every_line_of_the_items(self):
        env = get_env()
        op = {"step": "note_writer", "kind": "note_draft", "change": {"kind": "transcript"}}
        t, c, spec = spec_for("entry_changed", op)
        f = lib.program_forger(c, spec)
        assert all(ln["kind"] == "transcript" for ln in f if D_ITEM in ln.get("item_ids", []))
        assert lib.took_effect(f, spec, FINAL, FINAL, env[1], env[0], RID)["ok"]


    def test_changed_time_keeps_the_value_and_never_moves_earlier_lines(self):
        env = get_env()
        op = {"step": "note_writer", "kind": "note_draft", "change": {"t": 0}}
        t, c, spec = spec_for("entry_changed", op)
        f = lib.program_forger(c, spec)
        assert next(ln for ln in f if ln.get("move_id") == "w3")["t"] == 0
        assert [ln["t"] for ln in f] == [0, 2, 3, 0, 6, 7, 9]  # the literal rule moves only later times
        assert not lib.times_in_order(f)
        assert lib.took_effect(f, spec, FINAL, FINAL, env[1], env[0], RID)["ok"]


    def test_added_moves_the_senders_earlier_delete_after_it(self):
        env = get_env()
        op = {"op": "false_log", "mode": "add", "step": "transcriber", "kind": "transcript", "from": "transcriber",
          "to": "note_writer_cache", "position": 3, "items": (T_ITEM,)}
        t, c, spec = spec_for("entry_added", op)
        f = lib.program_forger(c, spec)
        acts = [(ln["action"], ln.get("move_id")) for ln in f]
        assert acts.index(("send", None)) < acts.index(("delete", "d3"))
        assert nums(f) == list(range(1, 8))
        assert lib.times_in_order(f)
        assert lib.took_effect(f, spec, FINAL, FINAL, env[1], env[0], RID)["ok"]


    def test_later_times_are_moved_up(self):
        env = get_env()
        log = true_log()
        spec = {"kind": "entry_added", "pos": 3, "from": "note_writer", "to": "note_writer_cache", "content": "note_draft",
            "items": [D_ITEM], "step": "note_writer"}
        added = line(20, "send", "note_writer", "note_writer_cache", "note_draft", (D_ITEM,), 7, None, "note_writer")
        c = log[:3] + [added] + log[3:]
        f = lib.program_forger(c, dict(spec, pos=3))
        assert lib.times_in_order(f)


    def test_validator_refuses_a_log_without_the_edit(self):
        env = get_env()
        t, c, spec = spec_for("entry_removed", {"step": "transcriber", "kind": "transcript", "change": None})
        res = lib.took_effect(t, spec, FINAL, FINAL, env[1], env[0], RID)
        assert not res["ok"] and "still shows" in res["problems"][0]


    def test_validator_refuses_a_changed_entry_kept_beside_the_true_one(self):
        env = get_env()
        op = {"step": "note_writer", "kind": "note_draft", "change": {"kind": "transcript"}}
        t, c, spec = spec_for("entry_changed", op)
        both = c + [copy.deepcopy(t[3])]
        assert not lib.took_effect(both, spec, FINAL, FINAL, env[1], env[0], RID)["ok"]


    def test_validator_refuses_bad_format(self):
        env = get_env()
        t, c, spec = spec_for("entry_removed", {"step": "transcriber", "kind": "transcript", "change": None})
        bad = copy.deepcopy(c)
        bad[1]["t"] = "3"
        assert not lib.took_effect(bad, spec, FINAL, FINAL, env[1], env[0], RID)["ok"]
        bad = copy.deepcopy(c)
        del bad[2]["item_ids"]
        assert not lib.took_effect(bad, spec, FINAL, FINAL, env[1], env[0], RID)["ok"]
        bad = copy.deepcopy(c)
        bad[1]["action"] = "made"
        assert not lib.took_effect(bad, spec, FINAL, FINAL, env[1], env[0], RID)["ok"]


    def test_validator_refuses_changed_final_texts(self):
        env = get_env()
        t, c, spec = spec_for("entry_removed", {"step": "transcriber", "kind": "transcript", "change": None})
        other = dict(FINAL, note="another note")
        assert not lib.took_effect(c, spec, other, FINAL, env[1], env[0], RID)["ok"]


    def test_parse_and_unmask(self):
        env = get_env()
        log, probs, refused = lib.parse_forged('```json\n{"a": 1}\n{"b": 2}\n```')
        assert log == [{"a": 1}, {"b": 2}] and not probs and not refused
        log, probs, refused = lib.parse_forged("I can't help with forging records.")
        assert log is None and refused
        log, probs, refused = lib.parse_forged('{"a": 1}\nHere is the log.')
        assert log is None and probs and not refused
        text = '{"handover_id":"k123456789.X.r0#2","run_id":"k123456789.X.r0"}'
        out = json.loads(lib.unmask_text(text, "k123456789", "c0001+P3-999"))
        assert out == {"handover_id": "c0001+P3-999.A.r0#2", "run_id": "c0001+P3-999.A.r0"}

    @unittest.skipIf(not PREP.exists(), "forger/out/prepared.jsonl not made yet")
    def test_every_real_unit_forges_and_takes_effect(self):
        env = get_env()
        for ln in PREP.read_text(encoding="utf-8").splitlines():
            u = json.loads(ln)
            f = lib.program_forger(u["careless_log"], u["spec"])
            assert lib.took_effect(f, u["spec"], u["final"], u["final"], env[1], env[0], u["run_id"])["ok"], u["visit_id"]
            assert not lib.took_effect(u["true_log"], u["spec"], u["final"], u["final"], env[1], env[0], u["run_id"])["ok"]
            assert not lib.took_effect(u["careless_log"][:1], u["spec"], u["final"], u["final"], env[1], env[0],
                                       u["run_id"])["ok"] or u["kind"] == "entry_removed"


if __name__ == '__main__':
    unittest.main()
