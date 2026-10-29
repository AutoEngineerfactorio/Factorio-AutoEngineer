"""Persistent local blueprint library with folders and nested Factorio books.

Immutable document verification uses the existing R07 codec. The library keeps
one bounded manifest and one validated exchange file per blueprint/book.
Writes are atomic and rooted under the caller's explicitly supplied directory.
No game access, no network calls, no modification of other saves.
"""
from __future__ import annotations

import json
import os
import tempfile
import uuid
from pathlib import Path

from blueprint_document import decode, describe
from blueprint_encoder import encode_document

MAX_RECORDS = 500
MAX_NAME = 96
MAX_MANIFEST_BYTES = 256000


class LibraryError(ValueError):
    """The local library refused the operation."""


def _title(name: object) -> str:
    if not isinstance(name, str):
        raise LibraryError("Name must be text")
    name = name.strip()
    if not 1 <= len(name) <= MAX_NAME or any(ch in name for ch in "\x00\r\n\\/"):
        raise LibraryError("Name must be 1-96 printable single-line characters")
    return name


def _atomic(path: Path, data: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8",
                                     dir=path.parent, prefix=".ae-",
                                     suffix=".tmp", delete=False) as file:
        tmp = Path(file.name)
        try:
            file.write(data)
            file.flush()
            os.fsync(file.fileno())
        except Exception:
            tmp.unlink(missing_ok=True)
            raise
    try:
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)


class BlueprintLibrary:
    """Local persistent folder tree and faithful blueprint/book documents."""

    def __init__(self, root: Path):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.records: dict[str, dict] = {}
        manifest = self.root / "index.json"
        if manifest.exists():
            if manifest.stat().st_size > MAX_MANIFEST_BYTES:
                raise LibraryError("Library index exceeds safety limit")
            data = json.loads(manifest.read_text(encoding="utf-8"))
            if not isinstance(data, dict) or data.get("schema") != 1:
                raise LibraryError("Unsupported blueprint library schema")
            rows = data.get("items")
            if not isinstance(rows, list) or len(rows) > MAX_RECORDS:
                raise LibraryError("Invalid library item count")
            for row in rows:
                if not isinstance(row, dict) or row.get("kind") not in (
                        "folder", "blueprint", "blueprint_book"):
                    raise LibraryError("Invalid library item")
                uid = row.get("id")
                if not isinstance(uid, str) or len(uid) != 32 or any(
                        ch not in "0123456789abcdef" for ch in uid):
                    raise LibraryError("Invalid library identifier")
                _title(row.get("name"))
                if uid in self.records:
                    raise LibraryError("Duplicate library identifier")
                self.records[uid] = dict(row)
            for row in self.records.values():
                parent = row.get("parent")
                if parent is not None and (
                    parent not in self.records or
                    self.records[parent]["kind"] != "folder"
                ):
                    raise LibraryError("Orphaned library entry")

    def _save(self) -> None:
        rows = list(self.records.values())
        if len(rows) > MAX_RECORDS:
            raise LibraryError("Library capacity reached")
        payload = json.dumps({"schema": 1, "items": rows},
                             ensure_ascii=False, separators=(",", ":"))
        if len(payload.encode("utf-8")) > MAX_MANIFEST_BYTES:
            raise LibraryError("Library index too large")
        _atomic(self.root / "index.json", payload)

    def children(self, parent: str | None = None) -> list[dict]:
        return sorted([dict(row) for row in self.records.values()
                       if row.get("parent") == parent],
                      key=lambda x: (x["kind"] != "folder",
                                     x["name"].casefold(), x["id"]))

    def _parent(self, parent: str | None):
        if parent is not None and (
            parent not in self.records or
            self.records[parent]["kind"] != "folder"
        ):
            raise LibraryError("Destination must be a library folder")

    def add_folder(self, name: str, parent: str | None = None) -> str:
        self._parent(parent)
        uid = uuid.uuid4().hex
        self.records[uid] = {
            "id": uid, "kind": "folder", "name": _title(name), "parent": parent,
        }
        try:
            self._save()
        except Exception:
            self.records.pop(uid, None)
            raise
        return uid

    def add_document(self, name: str, document: dict,
                     parent: str | None = None) -> str:
        self._parent(parent)
        kind = describe(document)["kind"]
        encoded = encode_document(document)
        uid = uuid.uuid4().hex
        file = self.root / (uid + ".txt")
        _atomic(file, encoded + "\n")
        self.records[uid] = {
            "id": uid, "kind": kind, "name": _title(name), "parent": parent,
        }
        try:
            self._save()
        except Exception:
            self.records.pop(uid, None)
            file.unlink(missing_ok=True)
            raise
        return uid

    def import_exchange(self, name: str, exchange: str,
                        parent: str | None = None) -> str:
        return self.add_document(name, decode(exchange.strip()), parent)

    def document(self, uid: str) -> dict:
        row = self.records.get(uid)
        if not row or row["kind"] == "folder":
            raise LibraryError("Select a saved blueprint or book")
        file = self.root / (uid + ".txt")
        data = file.read_text(encoding="utf-8").strip()
        doc = decode(data)
        if describe(doc)["kind"] != row["kind"]:
            raise LibraryError("Saved document kind does not match the library")
        return doc

    def rename(self, uid: str, name: str) -> None:
        row = self.records.get(uid)
        if row is None:
            raise LibraryError("Unknown library entry")
        previous = row["name"]
        row["name"] = _title(name)
        try:
            self._save()
        except Exception:
            row["name"] = previous
            raise

    def move(self, uid: str, parent: str | None) -> None:
        self._parent(parent)
        row = self.records.get(uid)
        if row is None:
            raise LibraryError("Unknown library entry")
        ancestor = parent
        while ancestor is not None:
            if ancestor == uid:
                raise LibraryError("Cannot move a folder inside itself")
            ancestor = self.records[ancestor].get("parent")
        previous = row.get("parent")
        row["parent"] = parent
        try:
            self._save()
        except Exception:
            row["parent"] = previous
            raise

    def delete(self, uid: str) -> None:
        """Delete one item only; prevent accidentally deleting populated folders."""
        row = self.records.get(uid)
        if row is None:
            raise LibraryError("Unknown library entry")
        if any(child.get("parent") == uid for child in self.records.values()):
            raise LibraryError("Folder contains items: move them first")
        self.records.pop(uid)
        try:
            self._save()
        except Exception:
            self.records[uid] = row
            raise
        if row["kind"] != "folder":
            (self.root / (uid + ".txt")).unlink(missing_ok=True)

    def new_book(self, name: str, parent: str | None = None) -> str:
        doc = {"blueprint_book": {
            "item": "blueprint-book", "label": _title(name),
            "version": 562949954076672, "active_index": 0, "blueprints": [],
        }}
        return self.add_document(name, doc, parent)

    def append_to_book(self, book_id: str, doc: dict) -> int:
        """Append one blueprint or nested book while preserving nested properties."""
        book = self.document(book_id)
        if "blueprint_book" not in book:
            raise LibraryError("Destination must be a blueprint book")
        kind = describe(doc)["kind"]
        entries = book["blueprint_book"]["blueprints"]
        if len(entries) >= 1000:
            raise LibraryError("Book exceeds local editor entry limit")
        index = max([entry["index"] for entry in entries], default=-1) + 1
        entries.append({"index": index, kind: doc[kind]})
        result = encode_document(book)
        _atomic(self.root / (book_id + ".txt"), result + "\n")
        return index

    def replace_document(self, uid: str, doc: dict) -> None:
        row = self.records.get(uid)
        if row is None or row["kind"] != describe(doc)["kind"]:
            raise LibraryError("Document must keep its saved kind")
        _atomic(self.root / (uid + ".txt"), encode_document(doc) + "\n")

    @staticmethod
    def _book_location(book: dict, path: tuple[int, ...]):
        if not path or len(path) > 9 or any(type(p) is not int or p < 0 for p in path):
            raise LibraryError("Book entry path must contain bounded list positions")
        current = book
        for position in path[:-1]:
            if "blueprint_book" not in current:
                raise LibraryError("An intermediate book entry is not a book")
            entries = current["blueprint_book"]["blueprints"]
            if position >= len(entries):
                raise LibraryError("Book entry no longer exists")
            child = entries[position]
            if "blueprint_book" not in child:
                raise LibraryError("An intermediate entry is not a book")
            current = {"blueprint_book": child["blueprint_book"]}
        if "blueprint_book" not in current:
            raise LibraryError("Not a blueprint book")
        entries = current["blueprint_book"]["blueprints"]
        selected_index = path[len(path) - 1]
        if selected_index >= len(entries):
            raise LibraryError("Book entry no longer exists")
        return entries, selected_index

    def book_entry(self, book_id: str, path: tuple[int, ...]) -> dict:
        book = self.document(book_id)
        entries, index = self._book_location(book, path)
        row = entries[index]
        kind = "blueprint_book" if "blueprint_book" in row else "blueprint"
        return {kind: row[kind]}

    def edit_book_entry(self, book_id: str, path: tuple[int, ...],
                        operation: str, *, label: str = "") -> None:
        """Rename, remove or reorder nested book entries without touching game data."""
        if operation not in ("rename", "remove", "up", "down"):
            raise LibraryError("Unsupported book-entry operation")
        book = self.document(book_id)
        entries, position = self._book_location(book, path)
        if operation == "rename":
            entry = entries[position]
            kind = "blueprint_book" if "blueprint_book" in entry else "blueprint"
            entry[kind]["label"] = _title(label)
        elif operation == "remove":
            del entries[position]
        else:
            destination = position + (-1 if operation == "up" else 1)
            if destination < 0 or destination >= len(entries):
                raise LibraryError("Book entry is already at the edge")
            entries[position], entries[destination] = entries[destination], entries[position]
        self.replace_document(book_id, book)
