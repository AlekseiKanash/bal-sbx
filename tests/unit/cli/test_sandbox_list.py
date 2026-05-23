"""Tests for `bal-sbx sandbox list` and the table renderer."""

from __future__ import annotations

import bal_sbx.api as api_module
from bal_sbx.api import SandboxManager
from bal_sbx.cli.main import main
from bal_sbx.cli.output import emit_sandbox_table
from bal_sbx.core.identity import SandboxIdentity
from bal_sbx.core.metadata import SandboxMetadata
from bal_sbx.core.paths import PathLayout
from bal_sbx.core.status import SandboxStatus
from bal_sbx.registry.json_file import JsonFileRegistry


def _real_manager(tmp_path, fake_system_ops) -> SandboxManager:
    layout = PathLayout(
        home_root=str(tmp_path / "homes"),
        registry_path=str(tmp_path / "registry.json"),
    )
    return SandboxManager(
        system_ops=fake_system_ops,
        registry=JsonFileRegistry(layout.registry_path),
        path_layout=layout,
    )


def test_sandbox_list_empty_prints_message(capsys, tmp_path, fake_system_ops):
    manager = _real_manager(tmp_path, fake_system_ops)
    rc = main(["sandbox", "list"], manager_factory=lambda: manager)
    assert rc == 0
    out = capsys.readouterr().out
    assert "No sandboxes registered." in out


def test_sandbox_list_renders_entries_in_last_used_desc(
    capsys, monkeypatch, tmp_path, fake_system_ops
):
    manager = _real_manager(tmp_path, fake_system_ops)
    ws_a = tmp_path / "ws_a"
    ws_b = tmp_path / "ws_b"
    ws_a.mkdir()
    ws_b.mkdir()

    # Force two deterministic timestamps so ordering is reliable.
    fake_times = iter(
        ["2026-05-01T00:00:00+00:00", "2026-05-02T00:00:00+00:00"]
    )
    monkeypatch.setattr(api_module, "_now_iso", lambda: next(fake_times))

    manager.get_or_create(str(ws_a))
    manager.get_or_create(str(ws_b))  # newer last_used_at → first row

    rc = main(["sandbox", "list"], manager_factory=lambda: manager)
    assert rc == 0
    out = capsys.readouterr().out

    layout = PathLayout(
        home_root=str(tmp_path / "homes"),
        registry_path=str(tmp_path / "registry.json"),
    )
    id_a = SandboxIdentity.from_workspace(str(ws_a), layout).id
    id_b = SandboxIdentity.from_workspace(str(ws_b), layout).id

    assert id_a in out
    assert id_b in out
    assert out.index(id_b) < out.index(id_a)
    assert "ID" in out and "WORKSPACE" in out
    assert "STATUS" in out and "LAST USED" in out


def test_emit_sandbox_table_golden(capsys):
    rows = [
        (
            SandboxIdentity(
                id="bal_f81d4f",
                user="bal_f81d4f",
                workspace="/Users/me/work/foo",
                home="/Users/bal_f81d4f",
                workspace_link="/Users/bal_f81d4f/workspace",
            ),
            SandboxMetadata(
                workspace="/Users/me/work/foo",
                created_at="2026-05-23T13:15:00Z",
                last_used_at="2026-05-23T13:15:00Z",
            ),
            SandboxStatus.OK,
        ),
        (
            SandboxIdentity(
                id="bal_a1b2c3",
                user="bal_a1b2c3",
                workspace="/Users/me/work/bar",
                home="/Users/bal_a1b2c3",
                workspace_link="/Users/bal_a1b2c3/workspace",
            ),
            SandboxMetadata(
                workspace="/Users/me/work/bar",
                created_at="2026-05-22T09:00:00Z",
                last_used_at="2026-05-22T09:00:00Z",
            ),
            SandboxStatus.BROKEN_SYMLINK,
        ),
    ]
    emit_sandbox_table(rows)
    expected = (
        "ID         WORKSPACE          STATUS         LAST USED\n"
        "bal_f81d4f /Users/me/work/foo ok             2026-05-23T13:15:00Z\n"
        "bal_a1b2c3 /Users/me/work/bar broken_symlink 2026-05-22T09:00:00Z\n"
    )
    assert capsys.readouterr().out == expected
