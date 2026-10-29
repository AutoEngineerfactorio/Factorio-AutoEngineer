"""The cache context: what the cached content belongs to.

A cached observation is only valid for the content it was observed from.
Two profiles that run different modpacks, or the same profile before and
after a mod change, hold **different** content, so a cache entry from one
must never be served for the other.

This module builds the key that identifies the content a cache entry
belongs to:

* the **profile** — which installation, which mod configuration and which
  own directories;
* the **game version** — the Factorio version the content was observed
  with;
* the **mod fingerprint** — the identity of the enabled mods;
* the **surface** — the world the content was observed in;
* the **force** — the research state the content was observed with.

Every part of the key is *observed*. Nothing is invented and nothing is
guessed from a directory name: the game version comes from the
executable's file version and the fingerprint from the installation's own
mod list.

The limits come from the settings, so the cache sizes are configurable
rather than hardcoded. A limit that is missing or unsafe falls back to
the protective default, so a wrong setting can never make the cache
unbounded.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any, Mapping

#: The default number of entries one cache may hold.
DEFAULT_MAX_ENTRIES = 512

#: The default lifetime of one cache entry, in seconds.
DEFAULT_TTL_SECONDS = 300

#: The smallest cache that still does something.
MIN_CACHE_ENTRIES = 16

#: The largest cache that is still bounded.
MAX_CACHE_ENTRIES = 65536

#: The shortest entry lifetime.
MIN_TTL_SECONDS = 1

#: The longest entry lifetime.
MAX_TTL_SECONDS = 86400


def bounded_entries(value: Any, default: int = DEFAULT_MAX_ENTRIES) -> int:
    """Return a cache entry limit that is safe to use."""
    if type(value) is not int:
        return default
    if value < MIN_CACHE_ENTRIES:
        return MIN_CACHE_ENTRIES
    if value > MAX_CACHE_ENTRIES:
        return MAX_CACHE_ENTRIES
    return value


def bounded_ttl(value: Any, default: int = DEFAULT_TTL_SECONDS) -> int:
    """Return a cache lifetime that is safe to use."""
    if type(value) is not int:
        return default
    if value < MIN_TTL_SECONDS:
        return MIN_TTL_SECONDS
    if value > MAX_TTL_SECONDS:
        return MAX_TTL_SECONDS
    return value


@dataclass(frozen=True)
class CacheContext:
    """The identity of the content a cache entry belongs to.

    The context is compared as a whole. An entry whose context differs
    from the current one is **not** served, and the caches that hold one
    context drop their entries when the context changes.
    """

    profile: str = ""
    game_version: str = ""
    mod_fingerprint: str = ""
    surface: str = ""
    force: str = ""

    @classmethod
    def from_profile(cls, profile: Any, *,
                      surface: str = "", force: str = "") -> "CacheContext":
        """Build the context of a stored profile.

        The profile's own identifier, its game version and the fingerprint
        of its mods are used. A profile that cannot be read yields an
        empty context, which never matches a populated one.
        """
        identifier = getattr(profile, "identifier", "")
        version = getattr(profile, "game_version", "") or ""
        fingerprint = ""
        try:
            fingerprint = profile.fingerprint
        except Exception:
            fingerprint = ""
        return cls(
            profile=str(identifier),
            game_version=str(version),
            mod_fingerprint=str(fingerprint),
            surface=str(surface or ""),
            force=str(force or ""),
        )

    def with_surface(self, surface: str) -> "CacheContext":
        """Return the context of the same content on another surface."""
        return CacheContext(
            profile=self.profile, game_version=self.game_version,
            mod_fingerprint=self.mod_fingerprint, surface=str(surface or ""),
            force=self.force)

    def with_force(self, force: str) -> "CacheContext":
        """Return the context of the same content with another research state."""
        return CacheContext(
            profile=self.profile, game_version=self.game_version,
            mod_fingerprint=self.mod_fingerprint, surface=self.surface,
            force=str(force or ""))

    @property
    def key(self) -> str:
        """A short, stable key for this context."""
        digest = hashlib.sha256()
        for part in (self.profile, self.game_version, self.mod_fingerprint,
                     self.surface, self.force):
            digest.update(part.encode("utf-8"))
            digest.update(b"\0")
        return digest.hexdigest()[:32]

    @property
    def empty(self) -> bool:
        """Whether this context identifies nothing."""
        return not (self.profile or self.game_version or self.mod_fingerprint
                    or self.surface or self.force)

    def matches(self, other: "CacheContext") -> bool:
        """Whether a cached entry of this context may be served now."""
        if self.empty or other.empty:
            return False
        return self.key == other.key

    def as_dict(self) -> dict[str, str]:
        """Return the context as a plain dictionary.

        The fingerprint is shortened: the report only needs to show that
        two contexts differ, not the whole digest.
        """
        return {
            "profile": self.profile,
            "game_version": self.game_version,
            "mod_fingerprint": self.mod_fingerprint[:16],
            "surface": self.surface,
            "force": self.force,
        }


def current_context(
    manager: Any = None,
    *,
    surface: str = "",
    force: str = "",
) -> CacheContext:
    """Return the context of the currently selected profile.

    The manager's own selection decides, because that is the profile the
    application is talking about. A profile that cannot be read yields an
    empty context, so nothing is served from a cache that cannot prove
    what it holds.
    """
    try:
        if manager is None:
            from factorio_profiles import ProfileManager

            manager = ProfileManager()
        identifier = manager.selected
        if not identifier:
            return CacheContext(surface=str(surface or ""),
                                force=str(force or ""))
        profile = manager.load(identifier)
    except Exception:
        return CacheContext(surface=str(surface or ""),
                            force=str(force or ""))
    return CacheContext.from_profile(profile, surface=surface, force=force)


def limits(settings: Any = None) -> tuple[int, int]:
    """Return the cache entry limit and the entry lifetime in seconds."""
    if settings is None:
        try:
            from runtime_settings import cache_limits

            entries, ttl = cache_limits()
            return bounded_entries(entries), bounded_ttl(ttl)
        except Exception:
            return DEFAULT_MAX_ENTRIES, DEFAULT_TTL_SECONDS
    try:
        entries = settings.get("cache_max_entries")
        ttl = settings.get("cache_ttl_seconds")
    except Exception:
        return DEFAULT_MAX_ENTRIES, DEFAULT_TTL_SECONDS
    return bounded_entries(entries), bounded_ttl(ttl)


def describe(context: CacheContext) -> Mapping[str, Any]:
    """Return a JSON-safe description of a context."""
    return {
        "key": context.key,
        "profile": context.profile,
        "game_version": context.game_version,
        "mod_fingerprint": context.mod_fingerprint[:16],
        "surface": context.surface,
        "force": context.force,
        "empty": context.empty,
    }
