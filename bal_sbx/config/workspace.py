"""Per-workspace configuration stored at `<workspace>/.bal/config.json`.

Currently holds env vars only. Writes are atomic (temp + rename) to match
the registry's durability story.
"""

from __future__ import annotations

import json
import os

from bal_sbx.core.paths import PathLayout


class WorkspaceConfig:
    def __init__(self, workspace: str, layout: PathLayout) -> None:
        self._path = os.path.join(workspace, layout.workspace_config_file)

    @property
    def path(self) -> str:
        return self._path

    def env(self) -> dict[str, str]:
        data = self._load()
        env = data.get("env", {})
        return dict(env)

    def set_env(self, key: str, value: str) -> None:
        data = self._load()
        env = dict(data.get("env", {}))
        env[key] = value
        data["env"] = env
        self._save(data)

    def unset_env(self, key: str) -> None:
        data = self._load()
        env = dict(data.get("env", {}))
        if key not in env:
            return
        del env[key]
        data["env"] = env
        self._save(data)

    def _load(self) -> dict:
        if not os.path.exists(self._path):
            return {}
        with open(self._path, encoding="utf-8") as f:
            return json.load(f)

    def _save(self, data: dict) -> None:
        parent = os.path.dirname(self._path)
        if parent:
            os.makedirs(parent, exist_ok=True)
        tmp_path = self._path + ".tmp"
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, sort_keys=True)
        os.replace(tmp_path, self._path)
