"""Persistent sandbox tracking via a JSON file on disk.

File shape (current):

    {
      "global": { "env": {...}, "shared_tools": {...} },
      "sandboxes": { "<id>": {<SandboxMetadata.to_dict>}, ... }
    }

Legacy flat shape (`{"<id>": {<metadata>}, ...}`) is detected structurally
(no `global` / `sandboxes` keys) and migrated in-memory on load. The first
`_save` after such a read rewrites the file in the new shape.

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

from bal_sbx.core.config import SandboxConfig
from bal_sbx.core.errors import RegistryCorrupt
from bal_sbx.core.metadata import SandboxMetadata


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class JsonFileRegistry:
    def __init__(self, path: str) -> None:
        self._path = path

    def list(self) -> list[tuple[str, SandboxMetadata]]:
        return list(self._load_sandboxes().items())

    def get(self, identity_id: str) -> SandboxMetadata | None:
        return self._load_sandboxes().get(identity_id)

    def put(self, identity_id: str, metadata: SandboxMetadata) -> None:
        if metadata.last_used_at == "":
            metadata = replace(metadata, last_used_at=_now_iso())
        global_cfg, entries = self._load_all()
        entries[identity_id] = metadata
        self._save(global_cfg, entries)

    def delete(self, identity_id: str) -> bool:
        global_cfg, entries = self._load_all()
        if identity_id not in entries:
            return False
        del entries[identity_id]
        self._save(global_cfg, entries)
        return True

    def touch(self, identity_id: str) -> None:
        global_cfg, entries = self._load_all()
        if identity_id not in entries:
            return
        entries[identity_id] = replace(entries[identity_id], last_used_at=_now_iso())
        self._save(global_cfg, entries)

    def global_config(self) -> SandboxConfig:
        return self._load_all()[0]

    def set_global_config(self, cfg: SandboxConfig) -> None:
        _, entries = self._load_all()
        self._save(cfg, entries)

    def _load_sandboxes(self) -> dict[str, SandboxMetadata]:
        return self._load_all()[1]

    def _load_all(self) -> tuple[SandboxConfig, dict[str, SandboxMetadata]]:
        if not os.path.exists(self._path):
            return SandboxConfig(), {}
        try:
            with open(self._path, encoding="utf-8") as f:
                raw = json.load(f)
        except json.JSONDecodeError as exc:
            raise RegistryCorrupt(self._path) from exc
        if not isinstance(raw, dict):
            raise RegistryCorrupt(self._path)
        if "global" in raw or "sandboxes" in raw:
            global_data = raw.get("global", {})
            sandbox_data = raw.get("sandboxes", {})
        else:
            global_data = {}
            sandbox_data = raw
        global_cfg = SandboxConfig.from_dict(global_data)
        entries = {sid: SandboxMetadata.from_dict(data) for sid, data in sandbox_data.items()}
        return global_cfg, entries

    def _save(
        self,
        global_cfg: SandboxConfig,
        entries: dict[str, SandboxMetadata],
    ) -> None:
        parent = os.path.dirname(self._path)
        if parent:
            os.makedirs(parent, exist_ok=True)
        serialized = {
            "global": global_cfg.to_dict(),
            "sandboxes": {sid: meta.to_dict() for sid, meta in entries.items()},
        }
        tmp_path = self._path + ".tmp"
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(serialized, f, indent=2, sort_keys=True)
        os.replace(tmp_path, self._path)
