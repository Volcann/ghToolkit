from __future__ import annotations

import json
import math
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

from .errors import (
    GhCommandError,
    GhExecutionError,
    GhNotInstalledError,
    GhResponseError,
    GhTimeoutError,
)


def _diagnostic(value: bytes | str | None) -> str:
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return value or ""


class GhRunner:
    def __init__(self, timeout: float | None = 30.0, executable: str = "gh"):
        if timeout is not None and (
            isinstance(timeout, bool)
            or not isinstance(timeout, (int, float))
            or not math.isfinite(timeout)
            or timeout <= 0
        ):
            raise ValueError("timeout must be a positive finite number or None")
        if not isinstance(executable, str) or not executable or "\x00" in executable:
            raise ValueError("executable must be a nonempty path or command name")
        self.timeout = timeout
        self.executable = executable

    @property
    def available(self) -> bool:
        return shutil.which(self.executable) is not None

    def run_bytes(
        self,
        *args: str,
        input_data: bytes | None = None,
        cwd: str | Path | None = None,
    ) -> bytes:
        if any(not isinstance(arg, str) for arg in args):
            raise TypeError("each command argument must be a string")
        if any("\x00" in arg for arg in args):
            raise ValueError("command arguments cannot contain NUL characters")
        if input_data is not None and not isinstance(input_data, bytes):
            raise TypeError("input_data must be bytes or None")
        if cwd is not None:
            try:
                cwd = Path(cwd).expanduser().resolve()
                if not cwd.is_dir():
                    raise GhExecutionError(f"Working directory does not exist: {cwd}")
            except OSError as exc:
                raise GhExecutionError(
                    "Could not access the working directory"
                ) from exc

        env = os.environ.copy()
        env.pop("GH_FORCE_TTY", None)
        env.update(
            {
                "GH_PROMPT_DISABLED": "1",
                "GH_PAGER": "cat",
                "PAGER": "cat",
                "NO_COLOR": "1",
                "CLICOLOR": "0",
                "CLICOLOR_FORCE": "0",
                "GH_NO_UPDATE_NOTIFIER": "1",
                "GH_NO_EXTENSION_UPDATE_NOTIFIER": "1",
            }
        )
        command = [self.executable, *(args or ("version",))]
        try:
            result = subprocess.run(
                command,
                input=input_data,
                stdin=subprocess.DEVNULL if input_data is None else None,
                capture_output=True,
                check=True,
                timeout=self.timeout,
                cwd=cwd,
                env=env,
            )
        except FileNotFoundError as exc:
            raise GhNotInstalledError(
                f"Could not start {self.executable!r}; check its installation and PATH"
            ) from exc
        except subprocess.TimeoutExpired as exc:
            raise GhTimeoutError(
                exc.timeout, _diagnostic(exc.stdout), _diagnostic(exc.stderr)
            ) from exc
        except subprocess.CalledProcessError as exc:
            raise GhCommandError(
                exc.returncode, _diagnostic(exc.stderr), _diagnostic(exc.stdout)
            ) from exc
        except OSError as exc:
            raise GhExecutionError(f"Operating-system error running gh: {exc}") from exc
        return result.stdout

    def run(
        self,
        *args: str,
        input_text: str | None = None,
        cwd: str | Path | None = None,
    ) -> str:
        if input_text is not None and not isinstance(input_text, str):
            raise TypeError("input_text must be a string or None")
        raw = self.run_bytes(
            *args,
            input_data=input_text.encode("utf-8") if input_text is not None else None,
            cwd=cwd,
        )
        try:
            return raw.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise GhResponseError("gh output is not valid UTF-8") from exc

    def run_json(
        self,
        *args: str,
        input_text: str | None = None,
        cwd: str | Path | None = None,
    ) -> Any:
        text = self.run(*args, input_text=input_text, cwd=cwd)
        try:
            return json.loads(text)
        except json.JSONDecodeError as exc:
            raise GhResponseError("gh returned invalid JSON") from exc


def run_gh(*args: str, timeout: float | None = 30.0) -> str:
    return GhRunner(timeout=timeout).run(*args)
