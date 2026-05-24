"""Tests for `bal_sbx.cli.workspace.resolve_workspace`."""

from __future__ import annotations

import os

from bal_sbx.cli.workspace import resolve_workspace


def test_resolve_workspace_falls_back_to_cwd(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    assert resolve_workspace(None) == os.path.realpath(str(tmp_path))


def test_resolve_workspace_canonicalizes_explicit_path(tmp_path):
    target = tmp_path / "ws"
    target.mkdir()
    assert resolve_workspace(str(target)) == os.path.realpath(str(target))


def test_resolve_workspace_walks_up_to_workspace_config(monkeypatch, tmp_path):
    (tmp_path / ".bal").mkdir()
    (tmp_path / ".bal" / "config.json").write_text("{}")
    deep = tmp_path / "sub" / "deeper"
    deep.mkdir(parents=True)
    monkeypatch.chdir(deep)
    assert resolve_workspace(None) == os.path.realpath(str(tmp_path))


def test_resolve_workspace_ignores_bare_dot_bal_directory(monkeypatch, tmp_path):
    """`.bal/` without a `config.json` inside (e.g. `~/.bal/` global config dir)
    must not be treated as a workspace marker — otherwise any cwd under $HOME
    would resolve to $HOME as the workspace."""
    (tmp_path / ".bal").mkdir()
    (tmp_path / ".bal" / "sandboxes.json").write_text("{}")
    deep = tmp_path / "sub" / "deeper"
    deep.mkdir(parents=True)
    monkeypatch.chdir(deep)
    assert resolve_workspace(None) == os.path.realpath(str(deep))
