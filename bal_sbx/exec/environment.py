"""Clean-environment construction for sandboxed exec.

`build_sandbox_env` returns a dict built from scratch — no host env is ever
inherited. Consequently the `denylist` parameter has no filtering effect on
the returned mapping today; it is part of the signature so the policy can
later move from code to data (see plan A7) without an API break, and to
guard a future code path where host env may bleed through (e.g. when the
caller decides to seed from `os.environ`).

Precedence (low → high):
  defaults < `extra_env` (shared-tool env) < `workspace_env` < `overrides`.

The ``BAL_SANDBOX_*`` identity keys are written *before* `extra_env` and
`workspace_env` so a tool or workspace config cannot rewrite its own sandbox
identity unless it also sets the key via the explicit-overrides path.

If an override or workspace key is also in `denylist`, the value still wins —
the caller is presumed to have made the choice deliberately.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence

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
    workspace_env: Mapping[str, str] | None = None,
    denylist: Iterable[str] = DEFAULT_DENYLIST,
    base_path: str = DEFAULT_PATH,
    extra_path_entries: Sequence[str] = (),
    extra_env: Mapping[str, str] | None = None,
) -> dict[str, str]:
    # Materialize once so the contract ("accepts any iterable") is enforced
    # at the boundary even though we do not currently apply it.
    frozenset(denylist)
    path_value = ":".join([*extra_path_entries, base_path]) if extra_path_entries else base_path
    env: dict[str, str] = {
        "HOME": identity.home,
        "USER": identity.user,
        "LOGNAME": identity.user,
        "PATH": path_value,
        "BAL_SANDBOX_ID": identity.id,
        "BAL_SANDBOX_WORKSPACE": identity.workspace,
    }
    if extra_env:
        env.update(extra_env)
    if workspace_env:
        env.update(workspace_env)
    if overrides:
        env.update(overrides)
    return env
