"""A fake `codex` program for the tests of the outside model's part, and helpers shared by tests/test_outside*.py.

No real call is ever made: the tests write this script into a temporary folder and pass it as the codex program.
How it behaves is set by mode.json beside it. It reads the prompt on standard input, writes the reply to the file
named by -o and prints what the real program prints (a `model:` line, the line `codex`, the reply and `tokens used`).
"""
import json
import os
import stat
import sys
import tempfile
import unittest
from pathlib import Path

FAKE = r'''#!__PYTHON__
import json, os, re, sys
here = os.path.dirname(os.path.abspath(__file__))
mode = json.load(open(os.path.join(here, "mode.json")))
args = sys.argv[1:]
def opt(name):
    return args[args.index(name) + 1] if name in args else None
prompt = sys.stdin.read()
count_path = os.path.join(here, "count.txt")
n = int(open(count_path).read()) if os.path.exists(count_path) else 0
open(count_path, "w").write(str(n + 1))
with open(os.path.join(here, "calls.jsonl"), "a") as fh:
    fh.write(json.dumps({"args": args, "cwd": os.getcwd(), "listing": sorted(os.listdir(os.getcwd())),
                         "prompt": prompt}) + "\n")
if mode.get("limit"):
    sys.stderr.write("You have hit your usage limit. Try again later.\n")
    sys.exit(1)
if n < mode.get("fail_first", 0):
    sys.stderr.write("network error\n")
    sys.exit(1)
if mode.get("limit_after") is not None and n >= mode["limit_after"]:
    sys.stderr.write("You have hit your usage limit.\n")
    sys.exit(1)

def blocks(kind):
    out = {}
    for m in re.finditer(r"=====%s (\d+) BEGIN=====\n(.*?)\n=====%s \1 END=====" % (kind, kind), prompt, re.S):
        out[int(m.group(1))] = m.group(2)
    return out

def certainty(t):
    return t.count("(certain)") - t.count("(hedged)")

def rewrite(instr, t):
    if "no longer names any source" in instr:
        t = re.sub(r"\[source:[^\]]*\]", "", t)
        return re.sub(r"pmid:\d+", "", t)
    if "names a different source" in instr:
        return re.sub(r"pmid:\d+", "pmid:99999999", t)
    if "more certainty" in instr:
        return t + " (certain)"
    if "less certainty" in instr:
        return t + " (hedged)"
    if "nothing in it says that an AI wrote it" in instr:
        return "\n".join(l for l in t.split("\n") if "AI" not in l)
    if "suggesting that a person wrote it" in instr:
        return t.replace("[AI-generated]", "Reviewed by the clinic team.")
    return t

def out_blocks(kind, d):
    return "\n\n".join("=====%s %d BEGIN=====\n%s\n=====%s %d END=====" % (kind, k, v, kind, k) for k, v in sorted(d.items()))

if "Rewrite this text" in prompt or "Rewrite this text" in prompt.replace("\n", " "):
    instr = re.search(r"(Rewrite this text[^\n]*)", prompt).group(1)
    d = {k: rewrite(instr, v) for k, v in blocks("TEXT").items()}
    if mode.get("drop_second") and len(d) > 1:
        d.pop(2, None)
    reply = out_blocks("TEXT", d)
    if mode.get("never_parse"):
        reply = "I have rewritten the texts but forgot the lines."
elif "Which text states its main conclusion" in prompt:
    lines = []
    for k, v in blocks("PAIR").items():
        a = re.search(r"Text A:\n(.*?)\n\nText B:\n(.*)$", v, re.S)
        ca, cb = certainty(a.group(1)), certainty(a.group(2))
        lines.append("PAIR %d: %s" % (k, "A" if ca > cb else "B" if cb > ca else "same"))
    reply = "\n".join(lines)
elif "separate tasks" in prompt:
    d = {}
    for k, v in blocks("TASK").items():
        if "Rule 5." in v:
            d[k] = "LEVEL " + mode.get("level", "high")
        elif "Rule 4." in v:
            d[k] = "VERDICT kept"
        else:
            d[k] = "VERDICT " + mode.get("verdict6", "kept")
    reply = out_blocks("TASK", d)
else:
    reply = "RULE 1 | step: a | what is sent, kept or changed: x | what the log shows: y\nRULE 2 | step: b | what is sent, kept or changed: x | what the log shows: y\nRULE 3 | step: c | what is sent, kept or changed: x | what the log shows: y"
model = mode.get("model") or opt("-m")
if opt("-o") and not mode.get("no_o_file"):
    open(opt("-o"), "w").write(reply)
sys.stderr.write("OpenAI Codex v0.169.0\n--------\nworkdir: %s\nmodel: %s\nreasoning effort: %s\n--------\n" % (opt("-C"), model, "medium"))
sys.stdout.write("codex\n%s\ntokens used\n%s\n" % (reply, mode.get("tokens", "3,600")))
'''


def write_fake(folder, **mode):
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / "codex"
    path.write_text(FAKE.replace("__PYTHON__", sys.executable), encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR)
    set_mode(folder, **mode)
    return str(path)


def set_mode(folder, **mode):
    (Path(folder) / "mode.json").write_text(json.dumps(mode), encoding="utf-8")


def fake_calls(folder):
    p = Path(folder) / "calls.jsonl"
    return [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines()] if p.exists() else []


class FakeTestCase(unittest.TestCase):
    """A temporary folder, a fake codex in it, and the config choices."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.fake_dir = self.tmp / "fake"
        self.codex = write_fake(self.fake_dir)
        from custody import outside
        self.outside = outside
        self.choices = outside.load_choices()
        self.choices["outside"]["retry_wait_seconds"] = [0, 0]

    def tearDown(self):
        self._tmp.cleanup()


class SelfTest(unittest.TestCase):
    def test_the_fake_writes_a_script(self):
        with tempfile.TemporaryDirectory() as d:
            path = write_fake(d)
            self.assertTrue(os.access(path, os.X_OK))


if __name__ == "__main__":
    unittest.main()
