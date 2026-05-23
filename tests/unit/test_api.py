"""Unit tests for the public facade `SandboxManager`."""

from __future__ import annotations

import sys

import pytest

from bal_sbx.api import Capabilities, SandboxManager, SandboxMode
from bal_sbx.backends.user import UserSandbox
from bal_sbx.core.errors import SandboxNotFound
from bal_sbx.core.metadata import SandboxMetadata
from bal_sbx.core.paths import PathLayout
from bal_sbx.core.status import SandboxStatus
from bal_sbx.exec.launcher import DirectLauncher, SandboxedLauncher
from bal_sbx.registry.json_file import JsonFileRegistry


def _layout(tmp_path) -> PathLayout:
    return PathLayout(
        home_root=str(tmp_path / "homes"),
        registry_path=str(tmp_path / "registry.json"),
    )


def _registry(tmp_path) -> JsonFileRegistry:
    return JsonFileRegistry(str(tmp_path / "registry.json"))


def _manager(fake_system_ops, tmp_path) -> SandboxManager:
    return SandboxManager(
        system_ops=fake_system_ops,
        registry=_registry(tmp_path),
        path_layout=_layout(tmp_path),
    )


def _workspace(tmp_path):
    ws = tmp_path / "ws"
    ws.mkdir()
    return ws


# ---- capabilities -------------------------------------------------------

def test_capabilities_round_trip(fake_system_ops, tmp_path):
    manager = _manager(fake_system_ops, tmp_path)
    caps = manager.capabilities()
    assert isinstance(caps, Capabilities)
    assert caps.platform == sys.platform
    # NullPrivilegeBroker → False
    assert caps.can_sudo is False
    # FakeAclManager → True
    assert caps.acl_supported is True
    # We're on a supported platform during CI/local runs (linux/darwin)
    assert caps.unsupported_reason is None


# ---- resolve ------------------------------------------------------------

def test_resolve_is_deterministic(fake_system_ops, tmp_path):
    manager = _manager(fake_system_ops, tmp_path)
    ws = _workspace(tmp_path)
    first = manager.resolve(str(ws))
    second = manager.resolve(str(ws))
    assert first == second


def test_resolve_canonicalizes_relative_paths(fake_system_ops, tmp_path, monkeypatch):
    manager = _manager(fake_system_ops, tmp_path)
    ws = _workspace(tmp_path)
    monkeypatch.chdir(tmp_path)
    via_abs = manager.resolve(str(ws))
    via_rel = manager.resolve("ws")
    assert via_abs.id == via_rel.id
    assert via_abs.workspace == via_rel.workspace


def test_resolve_is_side_effect_free(fake_system_ops, tmp_path):
    manager = _manager(fake_system_ops, tmp_path)
    ws = _workspace(tmp_path)
    registry_path = tmp_path / "registry.json"

    for _ in range(100):
        manager.resolve(str(ws))

    assert not registry_path.exists()


# ---- get_or_create ------------------------------------------------------

def test_get_or_create_creates_sandbox(fake_system_ops, tmp_path):
    manager = _manager(fake_system_ops, tmp_path)
    ws = _workspace(tmp_path)
    sandbox = manager.get_or_create(str(ws))
    assert isinstance(sandbox, UserSandbox)
    assert sandbox.status() is SandboxStatus.OK


def test_get_or_create_registers_metadata(fake_system_ops, tmp_path):
    manager = _manager(fake_system_ops, tmp_path)
    ws = _workspace(tmp_path)
    sandbox = manager.get_or_create(str(ws))

    registry = _registry(tmp_path)
    stored = registry.get(sandbox.identity.id)
    assert stored is not None
    assert stored.workspace == sandbox.identity.workspace
    assert stored.created_at != ""
    assert stored.last_used_at != ""


def test_get_or_create_is_idempotent(fake_system_ops, tmp_path):
    manager = _manager(fake_system_ops, tmp_path)
    ws = _workspace(tmp_path)
    first = manager.get_or_create(str(ws))
    second = manager.get_or_create(str(ws))

    assert first.identity == second.identity
    entries = _registry(tmp_path).list()
    assert len(entries) == 1


def test_get_or_create_touches_last_used_at_on_second_call(fake_system_ops, tmp_path):
    manager = _manager(fake_system_ops, tmp_path)
    ws = _workspace(tmp_path)
    sandbox = manager.get_or_create(str(ws))

    registry = _registry(tmp_path)
    original = registry.get(sandbox.identity.id)
    assert original is not None
    # Force an older timestamp so the touch is observable.
    registry.put(
        sandbox.identity.id,
        SandboxMetadata(
            workspace=original.workspace,
            created_at=original.created_at,
            last_used_at="2000-01-01T00:00:00+00:00",
        ),
    )

    manager.get_or_create(str(ws))
    after = _registry(tmp_path).get(sandbox.identity.id)
    assert after is not None
    assert after.last_used_at > "2000-01-01T00:00:00+00:00"
    assert after.created_at == original.created_at


def test_get_or_create_unknown_kind_raises(fake_system_ops, tmp_path):
    manager = _manager(fake_system_ops, tmp_path)
    ws = _workspace(tmp_path)
    with pytest.raises(ValueError):
        manager.get_or_create(str(ws), kind="docker")


# ---- launcher -----------------------------------------------------------

def test_launcher_safe_returns_sandboxed_launcher(fake_system_ops, tmp_path):
    manager = _manager(fake_system_ops, tmp_path)
    ws = _workspace(tmp_path)
    launcher = manager.launcher(str(ws), mode=SandboxMode.SAFE)
    assert isinstance(launcher, SandboxedLauncher)


def test_launcher_safe_creates_sandbox(fake_system_ops, tmp_path):
    manager = _manager(fake_system_ops, tmp_path)
    ws = _workspace(tmp_path)
    manager.launcher(str(ws), mode=SandboxMode.SAFE)
    entries = _registry(tmp_path).list()
    assert len(entries) == 1


def test_launcher_unsafe_returns_direct_launcher(fake_system_ops, tmp_path):
    manager = _manager(fake_system_ops, tmp_path)
    ws = _workspace(tmp_path)
    launcher = manager.launcher(str(ws), mode=SandboxMode.UNSAFE)
    assert isinstance(launcher, DirectLauncher)


def test_launcher_unsafe_does_not_create_sandbox(fake_system_ops, tmp_path):
    manager = _manager(fake_system_ops, tmp_path)
    ws = _workspace(tmp_path)
    manager.launcher(str(ws), mode=SandboxMode.UNSAFE)
    assert _registry(tmp_path).list() == []
    assert fake_system_ops.users.users == set()


def test_launcher_defaults_to_safe(fake_system_ops, tmp_path):
    manager = _manager(fake_system_ops, tmp_path)
    ws = _workspace(tmp_path)
    launcher = manager.launcher(str(ws))
    assert isinstance(launcher, SandboxedLauncher)


def test_unsafe_is_shorthand_for_unsafe_launcher(fake_system_ops, tmp_path):
    manager = _manager(fake_system_ops, tmp_path)
    ws = _workspace(tmp_path)
    launcher = manager.unsafe(str(ws))
    assert isinstance(launcher, DirectLauncher)
    assert _registry(tmp_path).list() == []


# ---- list ---------------------------------------------------------------

def test_list_returns_entries_sorted_by_last_used_desc(fake_system_ops, tmp_path):
    manager = _manager(fake_system_ops, tmp_path)
    ws_a = tmp_path / "a"
    ws_a.mkdir()
    ws_b = tmp_path / "b"
    ws_b.mkdir()
    ws_c = tmp_path / "c"
    ws_c.mkdir()

    a = manager.get_or_create(str(ws_a))
    b = manager.get_or_create(str(ws_b))
    c = manager.get_or_create(str(ws_c))

    registry = _registry(tmp_path)
    registry.put(
        a.identity.id,
        SandboxMetadata(
            workspace=a.identity.workspace,
            created_at="2020-01-01T00:00:00+00:00",
            last_used_at="2020-01-01T00:00:00+00:00",
        ),
    )
    registry.put(
        b.identity.id,
        SandboxMetadata(
            workspace=b.identity.workspace,
            created_at="2022-01-01T00:00:00+00:00",
            last_used_at="2026-01-01T00:00:00+00:00",
        ),
    )
    registry.put(
        c.identity.id,
        SandboxMetadata(
            workspace=c.identity.workspace,
            created_at="2024-01-01T00:00:00+00:00",
            last_used_at="2024-01-01T00:00:00+00:00",
        ),
    )

    listed = manager.list()
    ids = [identity.id for identity, _meta, _status in listed]
    assert ids == [b.identity.id, c.identity.id, a.identity.id]


def test_list_includes_status(fake_system_ops, tmp_path):
    manager = _manager(fake_system_ops, tmp_path)
    ws = _workspace(tmp_path)
    sandbox = manager.get_or_create(str(ws))

    listed = manager.list()
    assert len(listed) == 1
    identity, meta, status = listed[0]
    assert identity.id == sandbox.identity.id
    assert meta.workspace == sandbox.identity.workspace
    assert status is SandboxStatus.OK


def test_list_empty_when_no_registry_entries(fake_system_ops, tmp_path):
    manager = _manager(fake_system_ops, tmp_path)
    assert manager.list() == []


# ---- destroy ------------------------------------------------------------

def test_destroy_removes_registry_entry(fake_system_ops, tmp_path):
    manager = _manager(fake_system_ops, tmp_path)
    ws = _workspace(tmp_path)
    sandbox = manager.get_or_create(str(ws))

    manager.destroy(str(ws))

    assert _registry(tmp_path).get(sandbox.identity.id) is None


def test_destroy_tears_down_via_system_ops(fake_system_ops, tmp_path):
    manager = _manager(fake_system_ops, tmp_path)
    ws = _workspace(tmp_path)
    sandbox = manager.get_or_create(str(ws))

    assert sandbox.identity.user in fake_system_ops.users.users
    assert sandbox.identity.home in fake_system_ops.home.homes
    assert sandbox.identity.user in fake_system_ops.acl.grants.get(
        sandbox.identity.workspace, set()
    )

    manager.destroy(str(ws))

    assert sandbox.identity.user not in fake_system_ops.users.users
    assert sandbox.identity.home not in fake_system_ops.home.homes
    assert sandbox.identity.user not in fake_system_ops.acl.grants.get(
        sandbox.identity.workspace, set()
    )


def test_destroy_unknown_workspace_raises(fake_system_ops, tmp_path):
    manager = _manager(fake_system_ops, tmp_path)
    ws = _workspace(tmp_path)
    with pytest.raises(SandboxNotFound):
        manager.destroy(str(ws))


# ---- constructor defaults ----------------------------------------------

def test_constructor_uses_provided_overrides(fake_system_ops, tmp_path):
    layout = _layout(tmp_path)
    registry = _registry(tmp_path)
    manager = SandboxManager(
        system_ops=fake_system_ops,
        registry=registry,
        path_layout=layout,
    )
    # No call to SystemOps.detect or PathLayout.default should have happened.
    assert manager.capabilities().platform == sys.platform
