"""Tests for rejudge/rejudge.py. No real model call: a stand-in `claude` program answers. Temporary folders only;
the practice run runs/trial2_e2 is only read (its files are hashed before and after)."""
import contextlib
import hashlib
import io
import json
import os
import shutil
import stat
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
RJ = HERE.parent
ROOT = RJ.parent
sys.path.insert(0, str(RJ))
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

import rejudge  # noqa: E402

PRACTICE = ROOT / "runs" / "trial2_e2"

FAKE = r'''#!%(py)s
import hashlib, json, os, sys
here = os.path.dirname(os.path.abspath(__file__))
cfg = json.load(open(os.path.join(here, "mode.json")))
args = sys.argv[1:]
if args[:2] == ["auth", "status"]:
    print(json.dumps({"loggedIn": True, "authMethod": "claude.ai"})); sys.exit(0)
if args == ["--version"]:
    print("9.9.9 (Claude Code)"); sys.exit(0)
prompt = sys.stdin.read()
model = args[args.index("--model") + 1]
with open(os.path.join(here, "asked.log"), "a") as fh:
    fh.write(hashlib.sha256(prompt.encode()).hexdigest() + "\n")
h = int(hashlib.sha256(prompt.encode()).hexdigest(), 16)
if cfg.get("fail_mod") and h %% cfg["fail_mod"] == 0:
    print(json.dumps({"is_error": True, "subtype": "error_during_execution", "result": "boom"})); sys.exit(1)
if cfg.get("fail_all"):
    print(json.dumps({"is_error": True, "subtype": "error_during_execution", "result": "boom"})); sys.exit(1)
reply = "VERDICT kept" if h %% 3 else "**Verdict: broken**"
if cfg.get("garbage_mod") and h %% cfg["garbage_mod"] == 1:
    reply = "I cannot tell."
print(json.dumps({"type": "result", "subtype": "success", "is_error": False, "result": reply + "\n",
                  "usage": {"input_tokens": 1, "output_tokens": 1},
                  "modelUsage": {model: {"inputTokens": 1, "outputTokens": 1}}}))
'''


def quiet(*argv):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        code = rejudge.main(list(argv))
    return code, buf.getvalue()


def tree_hash(folder):
    out = {}
    for p in sorted(Path(folder).rglob("*")):
        if p.is_file():
            out[str(p.relative_to(folder))] = hashlib.sha256(p.read_bytes()).hexdigest()
    return out


def jl(path):
    return [json.loads(x) for x in Path(path).read_text(encoding="utf-8").splitlines() if x.strip()]


def small_run(dest, n=3):
    """A run folder of the first n clean units of the practice run, every file cut down to them."""
    units = []
    for v in jl(PRACTICE / "visits.jsonl"):
        if "+" not in v["visit_id"] and len(units) < n:
            units.append(v["visit_id"])
    dest.mkdir(parents=True)

    def unit(row):
        return row.get("visit_id") or row["run_id"].split(".")[0]

    for rel in ("visits.jsonl", "results.jsonl", "signals.jsonl", "texts.jsonl", "own_log.jsonl", "judge.jsonl",
                "hidden/plan.jsonl", "hidden/truth.jsonl"):
        src = PRACTICE / rel
        if not src.exists():
            continue
        (dest / rel).parent.mkdir(parents=True, exist_ok=True)
        rows = [r for r in jl(src) if unit(r) in units]
        (dest / rel).write_text("".join(json.dumps(r, sort_keys=True) + "\n" for r in rows), encoding="utf-8")
    (dest / "journal").mkdir()
    for p in (PRACTICE / "journal").iterdir():
        if p.name.split(".")[0] in units:
            shutil.copy2(str(p), str(dest / "journal" / p.name))
    shutil.copy2(str(PRACTICE / "manifest.json"), str(dest / "manifest.json"))
    (dest / "unusable_visits.json").write_text("[]\n", encoding="utf-8")
    return units


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp_ctx = tempfile.TemporaryDirectory()
        self.tmp = Path(self.tmp_ctx.name)
        self.addCleanup(self.tmp_ctx.cleanup)
        self.run_dir = self.tmp / "run"
        self.units = small_run(self.run_dir)
        self.bin_dir = self.tmp / "bin"
        self.bin_dir.mkdir()
        self.bin = self.bin_dir / "claude"
        self.bin.write_text(FAKE % {"py": sys.executable}, encoding="utf-8")
        self.bin.chmod(self.bin.stat().st_mode | stat.S_IXUSR)
        self.mode()
        self.out = self.tmp / "second"

    def mode(self, **kw):
        (self.bin_dir / "mode.json").write_text(json.dumps(kw), encoding="utf-8")

    def build(self, *extra):
        return quiet("build", "--run", str(self.run_dir), "--out", str(self.out), *extra)

    def answer(self, *extra):
        return quiet("answer", "--dir", str(self.out), "--claude-bin", str(self.bin), "--workers", "2",
                     "--transient-waits", "0", *extra)

    def asked(self):
        p = self.bin_dir / "asked.log"
        return p.read_text().split() if p.exists() else []


class TestBuild(Base):
    def test_one_prompt_per_text_and_rule(self):
        before = tree_hash(self.run_dir)
        code, text = self.build()
        self.assertEqual(code, 0, text)
        texts = {}
        for r in jl(self.run_dir / "texts.jsonl"):
            it = r["item"]
            if it["kind"] in ("answer", "plan", "patient_note"):
                texts.setdefault((it["visit_id"], it["item_id"]), it)
        index = jl(self.out / "index.jsonl")
        self.assertEqual(len(index), 2 * len(texts))
        self.assertEqual({r["rule"] for r in index}, {4, 6})
        pending = {r["call_id"]: r for r in jl(self.out / "pending.jsonl")}
        self.assertEqual({r["call_id"] for r in index}, set(pending))
        for r in index:
            prompt = pending[r["call_id"]]["prompt"]
            self.assertNotIn("the prose of this text", prompt)
            self.assertNotIn("the prose", prompt)
            q = rejudge.questions()[r["rule"]]
            self.assertIn(q, prompt)
            self.assertIn("Rule %d." % r["rule"], prompt)
            self.assertIn("VERDICT kept", prompt)
            self.assertIn(texts[(r["visit_id"], r["item_id"])]["text"], prompt)
            self.assertIn(r["kind"], ("answer", "plan", "patient_note"))
            self.assertIn(r["case_kind"], ("graded", "stored"))
        self.assertLessEqual(len(pending), len(index))
        for cid, row in pending.items():
            self.assertEqual(row["prompt_fp"], rejudge.fingerprint(row["prompt"]))
        self.assertEqual(before, tree_hash(self.run_dir))

    def test_identical_prompts_share_a_call_id(self):
        # a text repeated under two item ids of one kind and visit gives two index rows and one call
        rows = jl(self.run_dir / "texts.jsonl")
        dup = json.loads(json.dumps(next(r for r in rows if r["item"]["kind"] == "answer")))
        dup["item"]["item_id"] = "dup0000000000001"
        with open(self.run_dir / "texts.jsonl", "a") as fh:
            fh.write(json.dumps(dup) + "\n")
        self.assertEqual(self.build()[0], 0)
        index = jl(self.out / "index.jsonl")
        by_item = {}
        for r in index:
            by_item.setdefault((r["item_id"], r["rule"]), r["call_id"])
        orig = dup["item"]["text"]
        same = [r for r in index if r["item_id"] == "dup0000000000001"]
        self.assertTrue(same)
        for r in same:
            twin = [x for x in index if x["rule"] == r["rule"] and x["item_id"] != r["item_id"]
                    and x["visit_id"] == r["visit_id"] and x["call_id"] == r["call_id"]]
            self.assertTrue(twin)
        self.assertLess(len(jl(self.out / "pending.jsonl")), len(index))

    def test_bad_rule_refused(self):
        self.assertEqual(self.build("--rules", "5")[0], 2)


class TestAnswer(Base):
    def test_answers_and_second_start_asks_nothing(self):
        self.build()
        n = len(jl(self.out / "pending.jsonl"))
        code, _ = self.answer()
        self.assertEqual(code, 0)
        self.assertEqual(len(jl(self.out / "answers.jsonl")), n)
        self.assertEqual(len(self.asked()), n)
        code, _ = self.answer()
        self.assertEqual(code, 0)
        self.assertEqual(len(self.asked()), n)  # nothing asked twice

    def test_failures_stay_pending_then_second_start_asks_only_those(self):
        self.build()
        n = len(jl(self.out / "pending.jsonl"))
        self.mode(fail_mod=3)
        code, _ = self.answer()
        self.assertEqual(code, 1)
        got = len(jl(self.out / "answers.jsonl"))
        self.assertTrue(0 < got < n)
        asked_first = len(self.asked())
        self.mode()
        code, _ = self.answer()
        self.assertEqual(code, 0)
        self.assertEqual(len(jl(self.out / "answers.jsonl")), n)
        self.assertEqual(len(self.asked()) - asked_first, n - got)

    def test_all_failing_is_exit_5(self):
        self.build()
        self.mode(fail_all=True)
        code, _ = self.answer()
        self.assertEqual(code, 5)
        self.assertFalse((self.out / "answers.jsonl").exists() and jl(self.out / "answers.jsonl"))

    def test_wrong_model_reply_not_stored(self):
        self.build()
        code, _ = quiet("answer", "--dir", str(self.out), "--claude-bin", str(self.bin), "--workers", "1",
                        "--model", "claude-opus-5-5", "--transient-waits", "0")
        self.assertEqual(code, 0)  # the stand-in answers as the model asked


class TestCollectScore(Base):
    def test_collect_and_score(self):
        run_before = tree_hash(self.run_dir)
        self.mode(garbage_mod=7)
        self.build()
        self.answer()
        copy = self.tmp / "copy"
        code, text = quiet("collect", "--dir", str(self.out), "--run", str(self.run_dir), "--copy", str(copy))
        self.assertEqual(code, 0, text)
        second = jl(self.out / "judge_second_pass.jsonl")
        index = jl(self.out / "index.jsonl")
        self.assertEqual(len(second), len(index))
        for r in second:
            self.assertEqual(set(r), {"visit_id", "item_id", "rule", "verdict", "judge", "prompt_id"})
            self.assertEqual(r["prompt_id"], "judge.v1+second_pass")
            self.assertIn(r["verdict"], ("kept", "broken", "undecided"))
        unread = jl(self.out / "unreadable.jsonl")
        self.assertEqual(sum(r["verdict"] == "undecided" for r in second), len(unread))
        self.assertTrue(unread)
        orig = jl(self.run_dir / "judge.jsonl")
        new = jl(copy / "judge.jsonl")
        self.assertEqual(len(orig), len(new))
        o5 = [r for r in orig if r["rule"] == 5]
        n5 = [r for r in new if r["rule"] == 5]
        self.assertTrue(o5)
        self.assertEqual(o5, n5)
        self.assertEqual([r for r in new if r["rule"] in (4, 6)],
                         [next(s for s in second if (s["visit_id"], s["item_id"], s["rule"]) ==
                               (r["visit_id"], r["item_id"], r["rule"])) for r in orig if r["rule"] in (4, 6)])
        code, text = quiet("score", "--copy", str(copy))
        self.assertEqual(code, 0, text)
        self.assertTrue(text.strip())  # a practice-only run has no GRADES section: the text up to ENTRY ERRORS shows
        self.assertNotIn("ENTRY ERRORS", text)
        self.assertTrue((copy / "scores_second_pass.json").exists())
        self.assertTrue((copy / "scores_second_pass.txt").exists())
        # refusals
        self.assertEqual(quiet("collect", "--dir", str(self.out), "--run", str(self.run_dir),
                               "--copy", str(self.run_dir))[0], 2)
        self.assertEqual(quiet("collect", "--dir", str(self.out), "--run", str(self.run_dir),
                               "--copy", str(copy))[0], 2)
        self.assertEqual(quiet("collect", "--dir", str(self.out), "--run", str(self.run_dir),
                               "--copy", str(copy), "--force")[0], 0)
        self.assertEqual(run_before, tree_hash(self.run_dir))

    def test_collect_refuses_missing_answers(self):
        self.build()
        self.mode(fail_mod=3)
        self.answer()
        code, _ = quiet("collect", "--dir", str(self.out), "--run", str(self.run_dir), "--copy", str(self.tmp / "c"))
        self.assertEqual(code, 1)


class TestFrozenRunUntouched(unittest.TestCase):
    def test_whole_pipeline_leaves_the_practice_run_alone(self):
        before = tree_hash(PRACTICE)
        with tempfile.TemporaryDirectory() as t:
            t = Path(t)
            bin_dir = t / "bin"
            bin_dir.mkdir()
            b = bin_dir / "claude"
            b.write_text(FAKE % {"py": sys.executable}, encoding="utf-8")
            b.chmod(b.stat().st_mode | stat.S_IXUSR)
            (bin_dir / "mode.json").write_text("{}", encoding="utf-8")
            out, copy = t / "o", t / "c"
            self.assertEqual(quiet("build", "--run", str(PRACTICE), "--out", str(out))[0], 0)
            self.assertEqual(quiet("answer", "--dir", str(out), "--claude-bin", str(b), "--workers", "4")[0], 0)
            self.assertEqual(quiet("collect", "--dir", str(out), "--run", str(PRACTICE), "--copy", str(copy))[0], 0)
            self.assertEqual(quiet("score", "--copy", str(copy))[0], 0)
        self.assertEqual(before, tree_hash(PRACTICE))


if __name__ == "__main__":
    unittest.main()
