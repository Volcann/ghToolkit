from __future__ import annotations

from typing import Iterable, Mapping

# Default alias groups for known team members
DEFAULT_ALIASES: dict[str, set[str]] = {
    "volcann": {
        "volcann",
        "mohsin ali",
        "mohsin",
        "mohsinmuhammad823@gmail.com",
    },
    "mohsin ali": {
        "volcann",
        "mohsin ali",
        "mohsin",
        "mohsinmuhammad823@gmail.com",
    },
    "mohsin": {
        "volcann",
        "mohsin ali",
        "mohsin",
        "mohsinmuhammad823@gmail.com",
    },
    "moin bukhari": {"moin bukhari", "moin", "mb"},
    "tayyab sami": {"tayyab sami", "tayyab", "ts"},
    "uzair maqsood": {"uzair maqsood", "uzair", "um"},
}


class AuthorRegistry:
    """Manages author aliases and performs flexible fuzzy matching across git logins, names, and emails."""

    def __init__(self, initial_aliases: Mapping[str, Iterable[str]] | None = None):
        self._aliases: dict[str, set[str]] = {}
        for key, aliases in DEFAULT_ALIASES.items():
            self._aliases[key.strip().lower()] = {a.strip().lower() for a in aliases}
        if initial_aliases:
            for key, aliases in initial_aliases.items():
                self.register(key, aliases)

    def register(self, author: str, aliases: Iterable[str]) -> None:
        key = author.strip().lower()
        alias_set = self._aliases.setdefault(key, {key})
        for alias in aliases:
            norm = alias.strip().lower()
            if norm:
                alias_set.add(norm)
                # Ensure reverse lookup consistency
                self._aliases.setdefault(norm, alias_set).update(alias_set)

    def get_aliases(self, author: str) -> set[str]:
        key = author.strip().lower()
        if key in self._aliases:
            return self._aliases[key]
        return {key}

    def is_match(
        self,
        target_author: str,
        name: str = "",
        email: str = "",
        login: str = "",
    ) -> bool:
        t = target_author.strip().lower()
        if not t:
            return False

        targets = self.get_aliases(t)

        name_lower = name.strip().lower()
        email_lower = email.strip().lower()
        login_lower = login.strip().lower()

        for item in targets:
            if not item:
                continue
            if (
                item == name_lower
                or item == email_lower
                or item == login_lower
                or (name_lower and item in name_lower)
                or (email_lower and item in email_lower)
                or (login_lower and item in login_lower)
                or (name_lower and name_lower in item)
                or (login_lower and login_lower in item)
            ):
                return True
        return False


_GLOBAL_REGISTRY = AuthorRegistry()


def is_author_match(
    target_author: str,
    name: str = "",
    email: str = "",
    login: str = "",
    custom_aliases: Mapping[str, Iterable[str]] | None = None,
) -> bool:
    """Check if git author name, email, or login matches the target author.

    Supports aliases, email matching, and case-insensitive substring comparisons.
    """
    if custom_aliases:
        reg = AuthorRegistry(custom_aliases)
        return reg.is_match(target_author, name=name, email=email, login=login)
    return _GLOBAL_REGISTRY.is_match(target_author, name=name, email=email, login=login)


def register_author_alias(author: str, aliases: Iterable[str]) -> None:
    """Register custom aliases globally for an author."""
    _GLOBAL_REGISTRY.register(author, aliases)
