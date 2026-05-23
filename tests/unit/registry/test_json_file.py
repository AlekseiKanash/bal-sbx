import json
import os
from datetime import datetime

import pytest

from bal_sbx.core.errors import RegistryCorrupt
from bal_sbx.core.metadata import SandboxMetadata
from bal_sbx.registry.json_file import JsonFileRegistry


def _meta(
    workspace: str = "/w",
    created: str = "2026-01-01T00:00:00+00:00",
    last: str = "2026-01-01T00:00:00+00:00",
    agent: str | None = "claude",
) -> SandboxMetadata:
    return SandboxMetadata(
        workspace=workspace,
        created_at=created,
        last_used_at=last,
        agent=agent,
    )


def test_list_on_nonexistent_file_returns_empty(tmp_path):
    reg = JsonFileRegistry(str(tmp_path / "sandboxes.json"))
    assert reg.list() == []


def test_get_on_nonexistent_file_returns_none(tmp_path):
    reg = JsonFileRegistry(str(tmp_path / "sandboxes.json"))
    assert reg.get("bal_abcdef") is None


def test_put_get_round_trip(tmp_path):
    reg = JsonFileRegistry(str(tmp_path / "sandboxes.json"))
    meta = _meta()
    reg.put("bal_abcdef", meta)
    assert reg.get("bal_abcdef") == meta


def test_put_persists_across_instances(tmp_path):
    path = str(tmp_path / "sandboxes.json")
    JsonFileRegistry(path).put("bal_abcdef", _meta())
    assert JsonFileRegistry(path).get("bal_abcdef") == _meta()


def test_list_returns_all_entries(tmp_path):
    reg = JsonFileRegistry(str(tmp_path / "sandboxes.json"))
    a = _meta(workspace="/a")
    b = _meta(workspace="/b")
    reg.put("bal_aaaaaa", a)
    reg.put("bal_bbbbbb", b)
    assert dict(reg.list()) == {"bal_aaaaaa": a, "bal_bbbbbb": b}


def test_put_empty_last_used_at_replaced_with_now(tmp_path):
    reg = JsonFileRegistry(str(tmp_path / "sandboxes.json"))
    meta = SandboxMetadata(
        workspace="/w",
        created_at="2026-01-01T00:00:00+00:00",
        last_used_at="",
        agent=None,
    )
    reg.put("bal_abcdef", meta)
    stored = reg.get("bal_abcdef")
    assert stored is not None
    assert stored.last_used_at != ""
    datetime.fromisoformat(stored.last_used_at)


def test_put_does_not_mutate_caller_input(tmp_path):
    reg = JsonFileRegistry(str(tmp_path / "sandboxes.json"))
    meta = SandboxMetadata(
        workspace="/w",
        created_at="2026-01-01T00:00:00+00:00",
        last_used_at="",
        agent=None,
    )
    reg.put("bal_abcdef", meta)
    assert meta.last_used_at == ""


def test_put_preserves_explicit_last_used_at(tmp_path):
    reg = JsonFileRegistry(str(tmp_path / "sandboxes.json"))
    explicit = "2025-06-15T12:00:00+00:00"
    meta = _meta(last=explicit)
    reg.put("bal_abcdef", meta)
    assert reg.get("bal_abcdef").last_used_at == explicit


def test_delete_present_returns_true(tmp_path):
    reg = JsonFileRegistry(str(tmp_path / "sandboxes.json"))
    reg.put("bal_abcdef", _meta())
    assert reg.delete("bal_abcdef") is True
    assert reg.get("bal_abcdef") is None


def test_delete_absent_returns_false(tmp_path):
    reg = JsonFileRegistry(str(tmp_path / "sandboxes.json"))
    assert reg.delete("bal_abcdef") is False


def test_delete_leaves_other_entries(tmp_path):
    reg = JsonFileRegistry(str(tmp_path / "sandboxes.json"))
    reg.put("bal_aaaaaa", _meta(workspace="/a"))
    reg.put("bal_bbbbbb", _meta(workspace="/b"))
    reg.delete("bal_aaaaaa")
    assert reg.get("bal_aaaaaa") is None
    assert reg.get("bal_bbbbbb") == _meta(workspace="/b")


def test_touch_advances_last_used_at(tmp_path):
    reg = JsonFileRegistry(str(tmp_path / "sandboxes.json"))
    initial = _meta(last="2020-01-01T00:00:00+00:00")
    reg.put("bal_abcdef", initial)
    reg.touch("bal_abcdef")
    after = reg.get("bal_abcdef")
    assert after is not None
    assert after.last_used_at >= initial.last_used_at
    assert not after.last_used_at.startswith("2020")


def test_touch_missing_entry_is_noop(tmp_path):
    reg = JsonFileRegistry(str(tmp_path / "sandboxes.json"))
    reg.touch("bal_abcdef")
    assert reg.list() == []


def test_atomic_write_failure_preserves_existing_file(tmp_path, monkeypatch):
    path = tmp_path / "sandboxes.json"
    reg = JsonFileRegistry(str(path))
    reg.put("bal_abcdef", _meta(workspace="/original"))
    original_bytes = path.read_bytes()

    def boom(src, dst):
        raise OSError("simulated crash during os.replace")

    monkeypatch.setattr(os, "replace", boom)
    with pytest.raises(OSError):
        reg.put("bal_xxxxxx", _meta(workspace="/new"))

    assert path.read_bytes() == original_bytes


def test_corruption_raises_registry_corrupt(tmp_path):
    path = tmp_path / "sandboxes.json"
    path.write_text("not json")
    reg = JsonFileRegistry(str(path))
    with pytest.raises(RegistryCorrupt):
        reg.list()


def test_parent_directory_auto_created(tmp_path):
    path = tmp_path / "deep" / "nested" / "registry.json"
    reg = JsonFileRegistry(str(path))
    reg.put("bal_abcdef", _meta())
    assert path.exists()
    assert reg.get("bal_abcdef") == _meta()


def test_on_disk_format_is_id_keyed_dict(tmp_path):
    path = tmp_path / "sandboxes.json"
    reg = JsonFileRegistry(str(path))
    reg.put("bal_abcdef", _meta())
    raw = json.loads(path.read_text())
    assert list(raw.keys()) == ["bal_abcdef"]
    assert raw["bal_abcdef"] == _meta().to_dict()
