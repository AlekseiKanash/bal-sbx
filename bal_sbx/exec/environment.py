"""Clean-environment construction for sandboxed exec.

`build_sandbox_env` returns a dict built from scratch — no host env is ever
inherited. Consequently the `denylist` parameter has no filtering effect on
the returned mapping today; it is part of the signature so the policy can
later move from code to data (see plan A7) without an API break, and to
guard a future code path where host env may bleed through (e.g. when the
caller decides to seed from `os.environ`).

`overrides` are applied last. If an override key is also in `denylist`, the
override still wins — the caller (e.g. workspace config) is presumed to have
made the choice deliberately.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping

from bal_sbx.core.identity import SandboxIdentity


DEFAULT_DENYLIST: tuple[str, ...] = (
    "AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "AWS_SESSION_TOKEN",
    "GITHUB_TOKEN", "GH_TOKEN",
    "ANTHROPIC_API_KEY", "OPENAI_API_KEY",
    "SSH_AUTH_SOCK", "SSH_AGENT_PID",
    "HISTFILE",
)
DEFAULT_PATH = "/usr/local/bin:/usr/bin:/bin"


def build_sandbox_env(
    identity: SandboxIdentity,
    overrides: Mapping[str, str] | None = None,
    denylist: Iterable[str] = DEFAULT_DENYLIST,
    base_path: str = DEFAULT_PATH,
) -> dict[str, str]:
    # Materialize once so the contract ("accepts any iterable") is enforced
    # at the boundary even though we do not currently apply it.
    frozenset(denylist)
    env: dict[str, str] = {
        "HOME": identity.home,
        "USER": identity.user,
        "LOGNAME": identity.user,
        "PATH": base_path,
        "BAL_SANDBOX_ID": identity.id,
        "BAL_SANDBOX_WORKSPACE": identity.workspace,
    }
    if overrides:
        env.update(overrides)
    return env
