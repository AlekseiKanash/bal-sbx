"""Tests for `bal_sbx.config.settings.Settings`."""

from __future__ import annotations

import textwrap

import pytest

import bal_sbx.config.settings as settings_module
from bal_sbx.config.settings import Settings
from bal_sbx.core.errors import ConfigInvalid
from bal_sbx.exec.environment import DEFAULT_DENYLIST


def test_defaults():
    s = Settings()
    assert s.privilege_mode == "cached"
    assert s.env_denylist == DEFAULT_DENYLIST
    assert s.registry_path is None


def test_load_returns_defaults_when_file_missing(tmp_path):
    target = tmp_path / "does_not_exist.toml"
    s = Settings.load(str(target))
    assert s == Settings()


def test_load_reads_all_fields(tmp_path):
    target = tmp_path / "sbx.toml"
    target.write_text(textwrap.dedent("""\
        privilege_mode = "per_operation"
        env_denylist = ["FOO", "BAR"]
        registry_path = "/tmp/custom.json"
    """))
    s = Settings.load(str(target))
    assert s.privilege_mode == "per_operation"
    assert s.env_denylist == ("FOO", "BAR")
    assert s.registry_path == "/tmp/custom.json"


def test_load_partial_file_keeps_defaults_for_unspecified(tmp_path):
    target = tmp_path / "sbx.toml"
    target.write_text('privilege_mode = "per_operation"\n')
    s = Settings.load(str(target))
    assert s.privilege_mode == "per_operation"
    assert s.env_denylist == DEFAULT_DENYLIST
    assert s.registry_path is None


def test_load_rejects_unknown_key(tmp_path):
    target = tmp_path / "sbx.toml"
    target.write_text('mystery_setting = "no"\n')
    with pytest.raises(ConfigInvalid, match="unknown setting: mystery_setting"):
        Settings.load(str(target))


def test_load_with_none_uses_default_path(tmp_path, monkeypatch):
    target = tmp_path / "sbx.toml"
    target.write_text('privilege_mode = "per_operation"\n')
    monkeypatch.setattr(
        settings_module.os.path,
        "expanduser",
        lambda p: str(target) if p.startswith("~") else p,
    )
    s = Settings.load(None)
    assert s.privilege_mode == "per_operation"


def test_load_with_none_returns_defaults_when_default_missing(tmp_path, monkeypatch):
    missing = tmp_path / "absent.toml"
    monkeypatch.setattr(
        settings_module.os.path,
        "expanduser",
        lambda p: str(missing) if p.startswith("~") else p,
    )
    s = Settings.load(None)
    assert s == Settings()
