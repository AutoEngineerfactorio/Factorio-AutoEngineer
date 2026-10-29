"""Local persistent Factorio blueprint and blueprint-book collection.

Stored entries are complete R07-validated exchange documents. Books preserve
their nested items and indices; a book edit re-encodes and revalidates the whole
document before atomically replacing its file. No in-game blueprint library is
queried, modified, or represented as synced.
"""
from __future__ import annotations

import json
import os
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from blueprint_document import decode, describe
from blueprint_encoder import encode_document

# Separate experimental standalone inspector storage. The actual three-pane
# BlueprintWorkspace owns .local/blueprint-library with another index schema.
DEFAULT_ROOT = Path(__file__).resolve().parents[1] / ".local" / "blueprint-studio-scratch"
MAX_LIBRARY_ENTRIES = 2000
DEFAULT_VERSION = (2 << 48) | (1 << 32) | (23 << 16)


def atomic_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=".blueprint-", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            stream.write(content)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def _safe_label(text: str, *, max_length: int = 100) -> str:
    if not isinstance(text, str):
        raise ValueError("Name must be text")
    name = text.strip()
    if not name or len(name) > max_length or any(ch in name for ch in "\r\n\0"):
        raise ValueError("Name must be 1–100 characters without newlines")
    return name


def _document_part(document: dict[str, Any]) -> dict[str, Any]:
    return document["blueprint"] if "blueprint" in document else document["blueprint_book"]


class BlueprintLibraryStore:
    def __init__(self, root: Path = DEFAULT_ROOT):
        self.root = Path(root)
        self.index = self.root / "index.json"
        self.entries: dict[str, dict[str, Any]] = {}
        self.load_index()

    def load_index(self) -> None:
        try:
            payload = json.loads(self.index.read_text(encoding="utf-8"))
            entries = payload.get("entries")
            if not isinstance(entries, list):
                return
            for entry in entries[:MAX_LIBRARY_ENTRIES]:
                if (isinstance(entry, dict)
                        and isinstance(entry.get("id"), str)
                        and len(entry["id"]) == 32
                        and all(ch in "0123456789abcdef" for ch in entry["id"])
                        and isinstance(entry.get("label"), str)
                        and isinstance(entry.get("folder"), str)
                        and isinstance(entry.get("kind"), str)):
                    if (self.root / (entry["id"] + ".txt")).is_file():
                        self.entries[entry["id"]] = entry
        except (OSError, ValueError, TypeError):
            self.entries = {}

    def _save_index(self) -> None:
        payload = {"version": 1, "entries": sorted(
            self.entries.values(), key=lambda row: (row["folder"], row["label"], row["id"]))}
        atomic_text(self.index, json.dumps(payload, indent=2) + "\n")

    def list_items(self) -> list[dict[str, Any]]:
        return sorted((dict(x) for x in self.entries.values()),
                      key=lambda e: (e["folder"], e["label"], e["id"]))

    def get(self, identifier: str) -> dict[str, Any]:
        if identifier not in self.entries:
            raise KeyError("Blueprint was not found in the local library")
        source = (self.root / (identifier + ".txt")).read_text(encoding="utf-8").strip()
        return decode(source)

    def get_exchange(self, identifier: str) -> str:
        return encode_document(self.get(identifier))

    def save(self, document: dict[str, Any], *, label: str | None = None,
             folder: str = "My Blueprints", identifier: str | None = None) -> str:
        raw = encode_document(document)
        checked = decode(raw)
        details = describe(checked)
        if len(self.entries) >= MAX_LIBRARY_ENTRIES and identifier is None:
            raise ValueError("Local library entry limit reached")
        label = _safe_label(label or str(_document_part(checked).get("label") or "Untitled"))
        folder = _safe_label(folder)
        if identifier is not None and identifier not in self.entries:
            raise KeyError("Existing library entry not found")
        item_id = identifier or uuid.uuid4().hex
        metadata = {
            "id": item_id,
            "kind": details["kind"],
            "label": label,
            "folder": folder,
            "saved_at": datetime.now(timezone.utc).isoformat(),
            "entity_count": details.get("entity_count"),
            "book_count": details.get("blueprint_count"),
        }
        atomic_text(self.root / (item_id + ".txt"), raw + "\n")
        self.entries[item_id] = metadata
        self._save_index()
        return item_id

    def import_exchange(self, exchange: str, *, label: str | None = None,
                        folder: str = "Imported") -> str:
        return self.save(decode(exchange.strip()), label=label, folder=folder)

    def create_book(self, label: str, *, folder: str = "My Books") -> str:
        label = _safe_label(label)
        return self.save({"blueprint_book": {
            "label": label, "version": DEFAULT_VERSION,
            "active_index": 0, "blueprints": [],
        }}, label=label, folder=folder)

    def add_to_book(self, book_id: str, item_id: str) -> int:
        if book_id == item_id:
            raise ValueError("Cannot add a book to itself")
        book = self.get(book_id)
        source = self.get(item_id)
        if "blueprint_book" not in book:
            raise ValueError("Destination is not a blueprint book")
        entries = book["blueprint_book"]["blueprints"]
        if len(entries) >= 512:
            raise ValueError("Book entry limit reached")
        next_index = max((e["index"] for e in entries), default=-1) + 1
        kind = "blueprint" if "blueprint" in source else "blueprint_book"
        entries.append({"index": next_index, kind: source[kind]})
        # Validates nested-book depth, sizes, and every entry before writing.
        self.save(book, identifier=book_id,
                  label=self.entries[book_id]["label"],
                  folder=self.entries[book_id]["folder"])
        return next_index

    def remove_book_item(self, book_id: str, index: int) -> bool:
        doc = self.get(book_id)
        if "blueprint_book" not in doc:
            raise ValueError("Not a blueprint book")
        entries = doc["blueprint_book"]["blueprints"]
        remaining = [x for x in entries if x["index"] != index]
        if len(remaining) == len(entries):
            return False
        doc["blueprint_book"]["blueprints"] = remaining
        if doc["blueprint_book"].get("active_index") == index:
            doc["blueprint_book"]["active_index"] = remaining[0]["index"] if remaining else 0
        self.save(doc, identifier=book_id,
                  label=self.entries[book_id]["label"],
                  folder=self.entries[book_id]["folder"])
        return True

    def rename(self, identifier: str, new_label: str) -> None:
        label = _safe_label(new_label)
        doc = self.get(identifier)
        _document_part(doc)["label"] = label
        self.save(doc, identifier=identifier,
                  label=label, folder=self.entries[identifier]["folder"])
