"""The Z3 script that model/gen_z3.py writes must not crash on a delete at a place that no move fills.

Before 15 Nov 2026 the script read the arrival tick of such a place with st.arr[key] and stopped with a
KeyError (PF06 and PF07, whose patches send the retry copy or the cached transcript elsewhere, so the
retry queue or the cache is never filled before its delete). The runs need Z3; without it they are skipped.
"""
import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from custody import prove as P  # noqa: E402

_spec = importlib.util.spec_from_file_location("gen_z3_unfilled", str(ROOT / "model" / "gen_z3.py"))
GEN = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(GEN)

WIRING = P.load_wiring()
CHOICES = P.load_choices()
with open(str(ROOT / "faults" / "practice" / "practice_faults.json"), encoding="utf-8") as _f:
    PRACTICE = {f["fault_id"]: f for f in json.load(_f)["faults"]}

try:
    import z3  # noqa: F401
    HAVE_Z3 = True
except ImportError:
    HAVE_Z3 = False


def _run(text):
    with tempfile.TemporaryDirectory() as tmp:
        p = Path(tmp) / "z.py"
        p.write_text(text, encoding="utf-8")
        r = subprocess.run([sys.executable, str(p)], capture_output=True, text=True, timeout=300)
    return r.returncode, (r.stdout + r.stderr)


class UnfilledDelete(unittest.TestCase):
    def test_arrival_is_read_with_a_default(self):
        text = GEN.generate(WIRING, CHOICES)
        self.assertNotIn("st.arr[key] + hold", text)
        self.assertIn("st.arr.get(key, IntVal(0)) + hold", text)

    @unittest.skipUnless(HAVE_Z3, "Z3 is not installed")
    def test_pf06_and_pf07_run_and_find_their_break(self):
        expect = {"PF06": "P1 send w3q to debug_bucket", "PF07": "P1 send w2c to training_store"}
        for fid, line in expect.items():
            wiring = P.apply_patch(WIRING, PRACTICE[fid]["patch"])
            code, out = _run(GEN.generate(wiring, CHOICES))
            self.assertEqual(code, 0, fid + ": " + out[-300:])
            self.assertTrue(out.startswith("sat"), fid)
            self.assertIn(line, out, fid)

    @unittest.skipUnless(HAVE_Z3, "Z3 is not installed")
    def test_clean_wiring_stays_unsat(self):
        code, out = _run(GEN.generate(WIRING, CHOICES))
        self.assertEqual(code, 0, out[-300:])
        self.assertTrue(out.startswith("unsat"))


if __name__ == "__main__":
    unittest.main()
