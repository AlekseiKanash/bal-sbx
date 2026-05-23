"""Tests for `bal_sbx.config.workspace.WorkspaceConfig`."""

from __future__ import annotations

import json

import pytest

import bal_sbx.config.workspace as workspace_module
from bal_sbx.config.workspace import WorkspaceConfig
from bal_sbx.core.paths import PathLayout


LAYOUT = PathLayout(home_root="/home", registry_path="/tmp/r.json")


def test_env_empty_when_file_missing(tmp_path):
    config = WorkspaceConfig(str(tmp_path), LAYOUT)
    assert config.env() == {}


def test_set_env_persists_across_instances(tmp_path):
    WorkspaceConfig(str(tmp_path), LAYOUT).set_env("FOO", "bar")
    fresh = WorkspaceConfig(str(tmp_path), LAYOUT)
    assert fresh.env() == {"FOO": "bar"}


def test_set_env_writes_to_expected_path(tmp_path):
    WorkspaceConfig(str(tmp_path), LAYOUT).set_env("FOO", "bar")
    cfg_path = tmp_path / ".bal" / "config.json"
    assert cfg_path.exists()
    raw = json.loads(cfg_path.read_text())
    assert raw["env"]["FOO"] == "bar"


def test_env_returns_fresh_dict_each_call(tmp_path):
    config = WorkspaceConfig(str(tmp_path), LAYOUT)
    config.set_env("FOO", "bar")
    a = config.env()
    b = config.env()
    a["FOO"] = "mutated"
    assert b["FOO"] == "bar"


def test_set_env_overwrites_existing_key(tmp_path):
    config = WorkspaceConfig(str(tmp_path), LAYOUT)
    config.set_env("FOO", "one")
    config.set_env("FOO", "two")
    assert config.env() == {"FOO": "two"}


def test_unset_env_removes_key(tmp_path):
    config = WorkspaceConfig(str(tmp_path), LAYOUT)
    config.set_env("FOO", "bar")
    config.set_env("BAZ", "qux")
    config.unset_env("FOO")
    assert config.env() == {"BAZ": "qux"}


def test_unset_missing_key_is_noop(tmp_path):
    config = WorkspaceConfig(str(tmp_path), LAYOUT)
    config.unset_env("NOPE")
    assert config.env() == {}


def test_atomic_write_failure_leaves_existing_file_untouched(tmp_path, monkeypatch):
    config = WorkspaceConfig(str(tmp_path), LAYOUT)
    config.set_env("FOO", "original")

    def boom(*args, **kwargs):
        raise RuntimeError("disk full")

    monkeypatch.setattr(workspace_module.os, "replace", boom)
    with pytest.raises(RuntimeError):
        config.set_env("FOO", "changed")

    fresh = WorkspaceConfig(str(tmp_path), LAYOUT)
    assert fresh.env() == {"FOO": "original"}
