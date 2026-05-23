"""Persistent sandbox tracking via a JSON file on disk.

Concurrency: each write is atomic (write to `<path>.tmp`, then `os.replace`),
but the registry takes no lock — concurrent writers race and the last one
wins. Step 11 may introduce a lockfile if multi-process safety becomes a
real requirement.
"""

from __future__ import annotations

import json
import os
from dataclasses import replace
from datetime import datetime, timezone

from bal_sbx.core.errors import RegistryCorrupt
from bal_sbx.core.metadata import SandboxMetadata


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class JsonFileRegistry:
    def __init__(self, path: str) -> None:
        self._path = path

    def list(self) -> list[tuple[str, SandboxMetadata]]:
        return list(self._load().items())

    def get(self, identity_id: str) -> SandboxMetadata | None:
        return self._load().get(identity_id)

    def put(self, identity_id: str, metadata: SandboxMetadata) -> None:
        if metadata.last_used_at == "":
            metadata = replace(metadata, last_used_at=_now_iso())
        entries = self._load()
        entries[identity_id] = metadata
        self._save(entries)

    def delete(self, identity_id: str) -> bool:
        entries = self._load()
        if identity_id not in entries:
            return False
        del entries[identity_id]
        self._save(entries)
        return True

    def touch(self, identity_id: str) -> None:
        entries = self._load()
        if identity_id not in entries:
            return
        entries[identity_id] = replace(entries[identity_id], last_used_at=_now_iso())
        self._save(entries)

    def _load(self) -> dict[str, SandboxMetadata]:
        if not os.path.exists(self._path):
            return {}
        try:
            with open(self._path, encoding="utf-8") as f:
                raw = json.load(f)
        except json.JSONDecodeError as exc:
            raise RegistryCorrupt(self._path) from exc
        return {sid: SandboxMetadata.from_dict(data) for sid, data in raw.items()}

    def _save(self, entries: dict[str, SandboxMetadata]) -> None:
        parent = os.path.dirname(self._path)
        if parent:
            os.makedirs(parent, exist_ok=True)
        serialized = {sid: meta.to_dict() for sid, meta in entries.items()}
        tmp_path = self._path + ".tmp"
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(serialized, f, indent=2, sort_keys=True)
        os.replace(tmp_path, self._path)
