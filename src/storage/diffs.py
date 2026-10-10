from __future__ import annotations

import hashlib
import os
import re
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path

from ..core.errors import DiffStorageError


@dataclass(frozen=True, slots=True)
class DiffResult:
    diff_path: Path
    markdown_path: Path
    text: str
    markdown: str

    def as_dict(self) -> dict[str, str]:
        return {
            "diff_path": str(self.diff_path),
            "markdown_path": str(self.markdown_path),
            "text": self.text,
            "markdown": self.markdown,
        }


class DiffStore:
    def __init__(self, root: str | Path = "temp"):
        self.root = Path(root).expanduser().resolve()

    def save(
        self, repository: str, kind: str, identifier: str, raw: bytes
    ) -> DiffResult:
        if kind not in {"commit", "pr"}:
            raise ValueError("kind must be commit or pr")  # noqa: TRY003
        if not isinstance(raw, bytes):
            raise TypeError("raw diff must be bytes")  # noqa: TRY003
        repo_key = re.sub(r"[^A-Za-z0-9_.-]", "_", repository)
        repo_key = (
            f"{repo_key[:100]}-{hashlib.sha256(repository.encode()).hexdigest()[:12]}"
        )
        identity = re.sub(r"[^A-Za-z0-9_.-]", "_", identifier)[:60] or "ref"
        identity += "-" + hashlib.sha256(identifier.encode()).hexdigest()[:12]
        text = raw.decode("utf-8", errors="replace")
        longest = max((len(run) for run in re.findall(r"`+", text)), default=0)
        fence = "`" * max(3, longest + 1)
        trailing = "" if text.endswith("\n") else "\n"
        markdown = f"{fence}diff\n{text}{trailing}{fence}\n"
        directory: Path | None = None
        try:
            parent = self.root / repo_key / kind
            parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            directory = Path(tempfile.mkdtemp(prefix=f"{identity}-", dir=parent))
            diff_path = directory / "changes.diff"
            markdown_path = directory / "changes.md"
            self._write(diff_path, raw)
            self._write(markdown_path, markdown.encode("utf-8"))
        except OSError as exc:
            if directory is not None:
                shutil.rmtree(directory, ignore_errors=True)
            raise DiffStorageError(  # noqa: TRY003
                f"Could not preserve diff under {self.root}"
            ) from exc
        return DiffResult(diff_path, markdown_path, text, markdown)

    @staticmethod
    def _write(path: Path, content: bytes) -> None:
        with path.open("xb") as handle:
            os.chmod(path, 0o600)
            handle.write(content)
