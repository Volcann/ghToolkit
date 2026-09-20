from __future__ import annotations


class GitHubError(RuntimeError):
    pass


class GhNotInstalledError(GitHubError):
    pass


class GhExecutionError(GitHubError):
    pass


class GhTimeoutError(GitHubError):
    def __init__(self, timeout: float | None, stdout: str = "", stderr: str = ""):
        self.timeout = timeout
        self.stdout = stdout
        self.stderr = stderr
        super().__init__(f"gh exceeded its {timeout}-second timeout")


class GhCommandError(GitHubError):
    def __init__(self, returncode: int, stderr: str, stdout: str = ""):
        self.returncode = returncode
        self.stderr = stderr
        self.stdout = stdout
        super().__init__(
            f"gh exited with status {returncode}; inspect .stderr for details"
        )


class GhResponseError(GitHubError):
    pass


class DiffStorageError(GitHubError):
    pass
