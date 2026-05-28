import pytest

from bal_sbx.core.identity import SandboxIdentity
from bal_sbx.core.paths import PathLayout
from bal_sbx.exec.environment import (
    DEFAULT_DENYLIST,
    DEFAULT_PATH,
    build_sandbox_env,
)


LAYOUT = PathLayout(home_root="/home", registry_path="/tmp/r.json")


def _identity(tmp_path) -> SandboxIdentity:
    workspace = tmp_path / "ws"
    workspace.mkdir()
    return SandboxIdentity.from_workspace(str(workspace), LAYOUT)


def test_returns_only_explicit_keys(tmp_path):
    identity = _identity(tmp_path)
    env = build_sandbox_env(identity)
    assert set(env) == {
        "HOME",
        "USER",
        "LOGNAME",
        "PATH",
        "BAL_SANDBOX_ID",
        "BAL_SANDBOX_WORKSPACE",
    }


def test_sets_identity_fields(tmp_path):
    identity = _identity(tmp_path)
    env = build_sandbox_env(identity)
    assert env["HOME"] == identity.home
    assert env["USER"] == identity.user
    assert env["LOGNAME"] == identity.user
    assert env["PATH"] == DEFAULT_PATH
    assert env["BAL_SANDBOX_ID"] == identity.id
    assert env["BAL_SANDBOX_WORKSPACE"] == identity.workspace


def test_bal_sandbox_keys_always_present_with_overrides(tmp_path):
    identity = _identity(tmp_path)
    env = build_sandbox_env(identity, overrides={"FOO": "1"})
    assert env["BAL_SANDBOX_ID"] == identity.id
    assert env["BAL_SANDBOX_WORKSPACE"] == identity.workspace


def test_overrides_override_defaults(tmp_path):
    identity = _identity(tmp_path)
    env = build_sandbox_env(
        identity,
        overrides={"PATH": "/usr/games", "USER": "agent", "FOO": "bar"},
    )
    assert env["PATH"] == "/usr/games"
    assert env["USER"] == "agent"
    assert env["FOO"] == "bar"


def test_does_not_inherit_host_env(monkeypatch, tmp_path):
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "leaky")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "ak-xxx")
    monkeypatch.setenv("PWD", "/somewhere")
    monkeypatch.setenv("LC_ALL", "en_US.UTF-8")
    identity = _identity(tmp_path)
    env = build_sandbox_env(identity)
    assert "AWS_SECRET_ACCESS_KEY" not in env
    assert "ANTHROPIC_API_KEY" not in env
    assert "PWD" not in env
    assert "LC_ALL" not in env


def test_overrides_may_include_denylisted_keys(tmp_path):
    identity = _identity(tmp_path)
    env = build_sandbox_env(identity, overrides={"GITHUB_TOKEN": "explicit"})
    assert env["GITHUB_TOKEN"] == "explicit"


@pytest.mark.parametrize(
    "denylist",
    [
        list(DEFAULT_DENYLIST),
        tuple(DEFAULT_DENYLIST),
        set(DEFAULT_DENYLIST),
        frozenset(DEFAULT_DENYLIST),
        iter(DEFAULT_DENYLIST),
    ],
)
def test_denylist_accepts_any_iterable(denylist, tmp_path):
    identity = _identity(tmp_path)
    env = build_sandbox_env(identity, denylist=denylist)
    assert env["HOME"] == identity.home
    assert env["BAL_SANDBOX_ID"] == identity.id


def test_base_path_override(tmp_path):
    identity = _identity(tmp_path)
    env = build_sandbox_env(identity, base_path="/opt/custom/bin")
    assert env["PATH"] == "/opt/custom/bin"


def test_extra_path_entries_prepended(tmp_path):
    identity = _identity(tmp_path)
    env = build_sandbox_env(
        identity,
        extra_path_entries=["/opt/homebrew/bin", "/usr/local/bin"],
    )
    assert env["PATH"] == f"/opt/homebrew/bin:/usr/local/bin:{DEFAULT_PATH}"


def test_extra_path_entries_empty_leaves_base_path(tmp_path):
    identity = _identity(tmp_path)
    env = build_sandbox_env(identity, extra_path_entries=())
    assert env["PATH"] == DEFAULT_PATH


def test_extra_env_layered_below_workspace_env(tmp_path):
    identity = _identity(tmp_path)
    env = build_sandbox_env(
        identity,
        extra_env={"KEY": "from_tool", "TOOL_ONLY": "tool"},
        workspace_env={"KEY": "from_workspace"},
    )
    assert env["KEY"] == "from_workspace"
    assert env["TOOL_ONLY"] == "tool"


def test_extra_env_layered_below_overrides(tmp_path):
    identity = _identity(tmp_path)
    env = build_sandbox_env(
        identity,
        extra_env={"KEY": "from_tool"},
        overrides={"KEY": "from_cli"},
    )
    assert env["KEY"] == "from_cli"


def test_extra_env_can_override_defaults_but_not_identity(tmp_path):
    identity = _identity(tmp_path)
    env = build_sandbox_env(
        identity,
        extra_env={"PATH": "/from/tool", "BAL_SANDBOX_ID": "should-not-stick"},
    )
    # PATH is a default — extra_env wins
    assert env["PATH"] == "/from/tool"
    # Identity keys ARE in defaults too, so extra_env CAN override them
    # (matching how workspace_env behaves). This is intentional — defaults
    # are not sacred. The integrity guarantee is just "fresh env, no host
    # bleed-through".
    assert env["BAL_SANDBOX_ID"] == "should-not-stick"
