"""Read and validate a completed, per-save Factorio catalog export."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

MAX_PAGE_BYTES = 4_000_000
MAX_PAGES = 10000


def read_save_catalog(directory: Path, *, expected_save_id: str | None = None,
                      game_version: str | None = None,
                      mod_signature: str | None = None) -> dict[str, Any] | None:
    """Read only a complete, consistent export. No partial page sets."""
    manifest_file = directory / "complete.json"
    if not manifest_file.is_file():
        return None
    try:
        meta = json.loads(manifest_file.read_text(encoding="utf-8"))
        save_id = meta["save_id"]
        count = meta["total_pages"]
        if not isinstance(save_id, str):
            return None
        parent_id = (directory.parent.name if directory.name.startswith("g")
                     else directory.name)
        if save_id != parent_id:
            return None
        if expected_save_id is not None and expected_save_id != save_id:
            return None
        if game_version is not None and meta.get("game_version") != game_version:
            return None
        if mod_signature is not None and meta.get("mod_signature") != mod_signature:
            return None
        if type(count) is not int or not 1 <= count <= MAX_PAGES:
            return None
        merged: dict[str, Any] | None = None
        capabilities: dict[str, Any] | None = None
        for page in range(1, count + 1):
            filename = directory / f"page-{page}.json"
            if not filename.is_file() or filename.stat().st_size > MAX_PAGE_BYTES:
                return None
            data = json.loads(filename.read_text(encoding="utf-8"))
            if data.get("status") != "ok":
                return None
            status = data.get("catalog_status")
            caps = data.get("capabilities")
            if not isinstance(status, dict) or status.get("page") != page:
                return None
            if status.get("total_pages") != count:
                return None
            if not isinstance(caps, dict):
                return None
            if merged is None:
                merged = data
                capabilities = dict(caps)
                for key in ("recipes", "research", "machines", "excluded"):
                    capabilities[key] = list(caps.get(key) or [])
            else:
                assert capabilities is not None
                for key in ("recipes", "excluded"):
                    capabilities[key].extend(caps.get(key) or [])
                # Each export page repeats the whole machine/research catalog.
                # Do not multiply hundreds of machines by every recipe page.
        if merged is None or capabilities is None:
            return None
        merged["capabilities"] = capabilities
        merged["catalog_status"] = {
            **merged["catalog_status"], "page": 1, "total_pages": 1
        }
        return merged
    except (OSError, UnicodeError, ValueError, KeyError, TypeError):
        return None


def newest_complete_catalog(root: Path, *, game_version: str | None = None
                            ) -> tuple[Path, dict[str, Any]] | None:
    """Find completed exports; caller must still verify the active save ID."""
    if not root.is_dir():
        return None
    for directory in sorted(
        (p for p in root.iterdir() if p.is_dir()
         and (p / "complete.json").exists()),
        key=lambda p: (p / "complete.json").stat().st_mtime,
        reverse=True,
    ):
        frame = read_save_catalog(directory, game_version=game_version)
        if frame is not None:
            return directory, frame
    return None


def read_active_catalog(root: Path, *, game_version: str | None = None
                        ) -> tuple[str, dict[str, Any]] | None:
    """Only display the save identified by the running mod's current marker."""
    import time

    marker = root / "current.json"
    try:
        if not marker.is_file() or time.time() - marker.stat().st_mtime > 30:
            return None
        value = json.loads(marker.read_text(encoding="utf-8"))
        save_id = value.get("save_id")
        signature = value.get("mod_signature")
        if not isinstance(save_id, str) or not save_id.isascii():
            return None
        if not (1 <= len(save_id) <= 80) or any(
            char not in "0123456789-" for char in save_id
        ):
            return None
        if not isinstance(signature, str) or not signature:
            return None
        frame = read_save_catalog(
            root / save_id, expected_save_id=save_id,
            game_version=game_version, mod_signature=signature)
        if frame is None:
            return None
        return save_id, frame
    except (OSError, ValueError, TypeError):
        return None



def read_active_pages(root: Path, *, after_page: int = 0,
                      max_pages: int = 16, game_version: str | None = None,
                      allow_stale: bool = False
                      ) -> tuple[str, str, int, list[dict[str, Any]]] | None:
    """Incrementally read validated pages for exactly the active save/generation."""
    import time

    marker = root / "current.json"
    try:
        if not marker.is_file():
            return None
        if not allow_stale and time.time() - marker.stat().st_mtime > 30:
            return None
        meta = json.loads(marker.read_text(encoding="utf-8"))
        save_id = meta.get("save_id")
        signature = meta.get("mod_signature")
        generation = meta.get("generation")
        if not isinstance(save_id, str) or not (1 <= len(save_id) <= 80):
            return None
        if any(c not in "0123456789-" for c in save_id):
            return None
        if type(generation) is not int or not 1 <= generation <= 1000000:
            return None
        if not isinstance(signature, str) or not signature:
            return None
        if game_version is not None and meta.get("game_version") != game_version:
            return None
        folder = root / save_id / f"g{generation}"
        pages: list[dict[str, Any]] = []
        total = 0
        for n in range(after_page + 1, after_page + 1 + max_pages):
            filename = folder / f"page-{n}.json"
            if not filename.is_file() or filename.stat().st_size > MAX_PAGE_BYTES:
                break
            page = json.loads(filename.read_text(encoding="utf-8"))
            status = page.get("catalog_status")
            caps = page.get("capabilities")
            if (page.get("status") != "ok" or not isinstance(status, dict)
                    or status.get("page") != n or not isinstance(caps, dict)
                    or status.get("status") != "ok"):
                break
            declared = status.get("total_pages")
            if type(declared) is not int or not 1 <= declared <= MAX_PAGES:
                break
            if total and total != declared:
                break
            total = declared
            pages.append(page)
            if n >= total:
                break
        return save_id, f"g{generation}", total, pages
    except (OSError, UnicodeError, ValueError, KeyError, TypeError):
        return None



def read_or_build_compiled(
    root: Path, cache_root: Path, *,
    save_id: str, generation: str, game_version: str | None,
    mod_signature: str,
) -> dict[str, Any] | None:
    """Validate completed pages, then reuse a compressed per-save snapshot."""
    import gzip

    source = root / save_id / generation
    manifest = source / "complete.json"
    if not manifest.is_file():
        return None
    try:
        meta = json.loads(manifest.read_text(encoding="utf-8"))
        if (meta.get("save_id") != save_id
                or meta.get("game_version") != game_version
                or meta.get("mod_signature") != mod_signature
                or meta.get("generation") != int(generation[1:])):
            return None
        destination = cache_root / save_id / f"{generation}.json.gz"
        if destination.is_file() and (
            destination.stat().st_mtime >= manifest.stat().st_mtime
        ):
            with gzip.open(destination, "rt", encoding="utf-8") as stream:
                result = json.load(stream)
            if (isinstance(result, dict)
                    and result.get("catalog_status", {}).get("status") == "ok"):
                return result
        result = read_save_catalog(
            source, expected_save_id=save_id,
            game_version=game_version, mod_signature=mod_signature)
        if result is None:
            return None
        destination.parent.mkdir(parents=True, exist_ok=True)
        staging = destination.with_suffix(".partial")
        try:
            with gzip.open(staging, "wt", encoding="utf-8") as stream:
                json.dump(result, stream, separators=(",", ":"))
            staging.replace(destination)
        finally:
            staging.unlink(missing_ok=True)
        return result
    except (OSError, UnicodeError, ValueError, KeyError, TypeError):
        return None
