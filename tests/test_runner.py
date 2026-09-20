import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from ghtoolkit import (
    GhCommandError,
    GhExecutionError,
    GhNotInstalledError,
    GhResponseError,
    GhRunner,
    GhTimeoutError,
    run_gh,
)


class RunnerTests(unittest.TestCase):
    def test_default_command_is_version(self):
        with patch(
            "ghtoolkit.runner.subprocess.run",
            return_value=subprocess.CompletedProcess([], 0, b"version\n"),
        ) as run:
            self.assertEqual(run_gh(), "version\n")
        args, kwargs = run.call_args
        self.assertEqual(args[0], ["gh", "version"])
        self.assertTrue(kwargs["check"])
        self.assertEqual(kwargs["timeout"], 30.0)
        self.assertEqual(kwargs["stdin"], subprocess.DEVNULL)
        self.assertNotIn("shell", kwargs)

    def test_live_subprocess_returns_unmodified_bytes(self):
        runner = GhRunner(executable=sys.executable)
        raw = runner.run_bytes(
            "-S", "-c", "import sys; sys.stdout.buffer.write(b'a\\r\\n\\t b  \\n')"
        )
        self.assertEqual(raw, b"a\r\n\t b  \n")

    def test_live_nonzero_exit_preserves_both_streams(self):
        with self.assertRaises(GhCommandError) as raised:
            GhRunner(executable=sys.executable).run(
                "-S",
                "-c",
                "import sys; print('partial'); print('denied', file=sys.stderr); sys.exit(4)",
            )
        self.assertEqual(raised.exception.returncode, 4)
        self.assertEqual(raised.exception.stderr, "denied\n")
        self.assertEqual(raised.exception.stdout, "partial\n")
        self.assertIsInstance(raised.exception.__cause__, subprocess.CalledProcessError)
        self.assertNotIn("denied", str(raised.exception))

    def test_live_timeout(self):
        with self.assertRaises(GhTimeoutError) as raised:
            GhRunner(timeout=0.2, executable=sys.executable).run(
                "-S", "-c", "import time; print('started', flush=True); time.sleep(5)"
            )
        self.assertEqual(raised.exception.timeout, 0.2)
        self.assertIsInstance(raised.exception.__cause__, subprocess.TimeoutExpired)

    def test_timeout_preserves_partial_diagnostics(self):
        timeout = subprocess.TimeoutExpired(
            "gh", 30.0, output=b"partial", stderr=b"details"
        )
        with patch("ghtoolkit.runner.subprocess.run", side_effect=timeout):
            with self.assertRaises(GhTimeoutError) as raised:
                GhRunner().run()
        self.assertEqual(raised.exception.stdout, "partial")
        self.assertEqual(raised.exception.stderr, "details")

    def test_missing_executable(self):
        with tempfile.TemporaryDirectory() as directory:
            runner = GhRunner(executable=str(Path(directory) / "missing-gh"))
            self.assertFalse(runner.available)
            with self.assertRaises(GhNotInstalledError):
                runner.run()

    @unittest.skipUnless(os.name == "posix", "POSIX permissions required")
    def test_permission_failure_is_not_not_installed(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "gh"
            path.write_text("not executable")
            path.chmod(0o600)
            with self.assertRaises(GhExecutionError) as raised:
                GhRunner(executable=str(path)).run()
            self.assertIsInstance(raised.exception.__cause__, PermissionError)

    def test_missing_working_directory_is_not_not_installed(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(GhExecutionError):
                GhRunner(executable=sys.executable).run(
                    "-V", cwd=Path(directory) / "missing"
                )

    def test_invalid_utf8_raises_response_error(self):
        with self.assertRaises(GhResponseError):
            GhRunner(executable=sys.executable).run(
                "-S", "-c", "import sys; sys.stdout.buffer.write(b'\\xff')"
            )

    def test_valid_json(self):
        self.assertEqual(
            GhRunner(executable=sys.executable).run_json("-S", "-c", "print('[1, 2]')"),
            [1, 2],
        )

    def test_invalid_json_is_not_empty_success(self):
        with self.assertRaises(GhResponseError):
            GhRunner(executable=sys.executable).run_json(
                "-S", "-c", "print('not JSON')"
            )

    def test_stdin_is_forwarded_without_a_shell(self):
        text = 'line one\n`literal` ; $HOME "quoted"'
        self.assertEqual(
            GhRunner(executable=sys.executable).run(
                "-S",
                "-c",
                "import sys; sys.stdout.write(sys.stdin.read())",
                input_text=text,
            ),
            text,
        )

    def test_default_stdin_is_closed(self):
        self.assertEqual(
            GhRunner(executable=sys.executable).run(
                "-S", "-c", "import sys; print(len(sys.stdin.read()))"
            ),
            "0\n",
        )

    def test_environment_disables_prompt_color_and_tty(self):
        with patch.dict(os.environ, {"GH_FORCE_TTY": "100%", "CLICOLOR_FORCE": "1"}):
            result = GhRunner(executable=sys.executable).run_json(
                "-S",
                "-c",
                "import os,json; print(json.dumps({k:os.getenv(k) for k in ['GH_FORCE_TTY','GH_PROMPT_DISABLED','NO_COLOR','CLICOLOR_FORCE']}))",
            )
        self.assertIsNone(result["GH_FORCE_TTY"])
        self.assertEqual(result["GH_PROMPT_DISABLED"], "1")
        self.assertEqual(result["NO_COLOR"], "1")
        self.assertEqual(result["CLICOLOR_FORCE"], "0")

    def test_invalid_timeouts(self):
        for timeout in (0, -1, True, float("nan"), float("inf"), "30"):
            with self.subTest(timeout=timeout), self.assertRaises(ValueError):
                GhRunner(timeout=timeout)
        self.assertIsNone(GhRunner(timeout=None).timeout)

    def test_invalid_argument_types_are_caller_errors(self):
        with self.assertRaises(TypeError):
            GhRunner().run(["pr", "list"])
        with self.assertRaises(ValueError):
            GhRunner().run("bad\x00argument")
        with self.assertRaises(TypeError):
            GhRunner().run_bytes("version", input_data="not bytes")
        with self.assertRaises(TypeError):
            GhRunner().run("version", input_text=b"not text")

    def test_available_checks_path(self):
        self.assertTrue(GhRunner(executable=sys.executable).available)

    def test_shell_metacharacters_remain_one_argument(self):
        value = "a; echo INJECTED $(whoami)"
        self.assertEqual(
            GhRunner(executable=sys.executable).run(
                "-S", "-c", "import sys; print(sys.argv[1])", value
            ),
            value + "\n",
        )
