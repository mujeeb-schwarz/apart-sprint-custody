"""Point 1 of the outside model's part: the caller (custody/outside.py, ask) with a fake codex program."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_outside_fake import FakeTestCase, fake_calls, set_mode  # noqa: E402


class TestAsk(FakeTestCase):
    def ask(self, prompt="hello", **kw):
        return self.outside.ask(prompt, choices=self.choices, codex_bin=self.codex, sleep=lambda s: None, **kw)

    def test_returns_text_model_and_tokens(self):
        r = self.ask("Say something")
        self.assertIsNone(r["error"])
        self.assertIn("RULE 1", r["text"])
        self.assertEqual(r["model"], "gpt-6.1-sol")
        self.assertEqual(r["tokens"], 3600)

    def test_the_command_has_the_settings_of_the_config(self):
        self.ask("hello")
        call = fake_calls(self.fake_dir)[0]
        a = call["args"]
        self.assertEqual(a[:4], ["exec", "--skip-git-repo-check", "-s", "read-only"])
        self.assertEqual(a[a.index("-m") + 1], "gpt-6.1-sol")
        self.assertIn("model_reasoning_effort=medium", a)
        self.assertIn("-C", a)
        self.assertIn("-o", a)
        self.assertEqual(call["prompt"], "hello")  # the prompt goes on standard input, not as an argument
        self.assertNotIn("hello", a)

    def test_each_call_runs_in_a_new_empty_folder(self):
        self.ask("one")
        self.ask("two")
        calls = fake_calls(self.fake_dir)
        self.assertEqual(calls[0]["listing"], [])
        self.assertEqual(calls[1]["listing"], [])
        self.assertNotEqual(calls[0]["cwd"], calls[1]["cwd"])
        self.assertEqual(Path(calls[0]["cwd"]).resolve(), Path(calls[0]["args"][calls[0]["args"].index("-C") + 1]).resolve())
        self.assertFalse(Path(calls[0]["cwd"]).exists())  # removed afterwards

    def test_text_after_the_line_codex_when_no_file_is_written(self):
        set_mode(self.fake_dir, no_o_file=True)
        r = self.ask("x")
        self.assertIsNone(r["error"])
        self.assertIn("RULE 2", r["text"])
        self.assertNotIn("tokens used", r["text"])

    def test_a_usage_limit_is_named_and_not_retried(self):
        set_mode(self.fake_dir, limit=True)
        r = self.ask("x")
        self.assertEqual(r["error"], "usage_limit")
        self.assertTrue(r["limit"])
        self.assertIsNone(r["text"])
        self.assertEqual(len(fake_calls(self.fake_dir)), 1)

    def test_a_failed_exit_is_retried_then_answers(self):
        set_mode(self.fake_dir, fail_first=2)
        waits = []
        r = self.outside.ask("x", choices=self.choices, codex_bin=self.codex, sleep=waits.append,
                             waits=[20, 60])
        self.assertIsNone(r["error"])
        self.assertEqual(r["attempts"], 3)
        self.assertEqual(waits, [20, 60])

    def test_gives_up_after_the_retries(self):
        set_mode(self.fake_dir, fail_first=99)
        r = self.ask("x", retries=1)
        self.assertEqual(r["error"], "exit 1")
        self.assertEqual(r["attempts"], 2)

    def test_another_model_named_is_an_error(self):
        set_mode(self.fake_dir, model="gpt-other")
        r = self.ask("x")
        self.assertEqual(r["error"], "wrong_model")
        self.assertEqual(r["model"], "gpt-other")
        self.assertIsNone(r["text"])

    def test_a_missing_program_is_an_error(self):
        r = self.outside.ask("x", choices=self.choices, codex_bin=str(self.tmp / "nothing_here"),
                             sleep=lambda s: None)
        self.assertEqual(r["error"], "no_program")

    def test_every_attempt_goes_to_the_log_without_the_prompt(self):
        rows = []
        set_mode(self.fake_dir, fail_first=1)
        self.ask("a secret prompt", log=rows.append, purpose="unit")
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["error"], "exit 1")
        self.assertIsNone(rows[1]["error"])
        self.assertNotIn("secret", str(rows))
        self.assertEqual(rows[1]["purpose"], "unit")

    def test_parse_output_reads_model_and_tokens(self):
        text, model, tokens = self.outside.parse_output("codex\nanswer\ntokens used\n12,345\n",
                                                        "model: gpt-6.1-sol\n", None)
        self.assertEqual((text, model, tokens), ("answer", "gpt-6.1-sol", 12345))
        text, model, tokens = self.outside.parse_output("", "", "from file\n")
        self.assertEqual((text, model, tokens), ("from file\n", None, None))

    def test_framed_batches_parse_strictly(self):
        c = self.choices
        reply = "\n".join([self.outside.frame(c, "text", 1, "one"), self.outside.frame(c, "text", 2, "two\nlines")])
        self.assertEqual(self.outside.parse_framed(c, reply, "text", [1, 2]), {1: "one", 2: "two\nlines"})
        # a missing end line: that text is not returned, the other is
        broken = reply.replace("=====TEXT 2 END=====", "")
        self.assertEqual(self.outside.parse_framed(c, broken, "text", [1, 2]), {1: "one"})
        # a number nobody asked for: nothing is returned
        self.assertEqual(self.outside.parse_framed(c, reply, "text", [1]), {})
        # the same begin line twice: that text is left out
        twice = reply + "\n" + self.outside.frame(c, "text", 1, "again")
        self.assertEqual(self.outside.parse_framed(c, twice, "text", [1, 2]), {2: "two\nlines"})


class TestConfig(FakeTestCase):
    def test_the_config_holds_the_outside_key(self):
        o = self.choices["outside"]
        self.assertEqual(o["model"], "gpt-6.1-sol")
        self.assertEqual(o["effort"], "medium")
        self.assertEqual(o["batch"], 8)
        self.assertEqual(o["judge_batch"], 5)
        self.assertEqual(o["confirm"]["min_similarity"], 0.8)
        self.assertEqual(set(o["instructions"]), set(o["kinds"]))

    def test_no_personal_name_or_address_in_a_prompt_or_the_key(self):
        text = "".join(p.read_text(encoding="utf-8") for p in (Path(__file__).resolve().parents[1] / "prompts").glob("outside_*.txt"))
        for bad in ("@",):  # the original also listed the author's name, left out of this public copy
            self.assertNotIn(bad, text.lower())


if __name__ == "__main__":
    unittest.main()
