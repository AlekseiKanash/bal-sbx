# bal-sbx

Secure-by-default sandboxing for AI coding agents.

`bal-sbx` runs agents like `claude`, `codex`, or `opencode` as dedicated, per-workspace UNIX users with an isolated `$HOME` and ACL-scoped access to the current project. The agent never sees `~/.ssh`, `~/.aws`, `~/.config`, shell history, or anything else in the host user's home.

It ships as both a Python library (consumed by [bal](../bal)) and a standalone CLI (`bal-sbx`) for testing and running arbitrary software inside a sandbox.

Status: **early development**. Implementing Phase 1 + Phase 2 of [`docs/bal_sandboxing_strategy.md`](docs/bal_sandboxing_strategy.md). See [`dev_roadmap/plan.md`](dev_roadmap/plan.md).

---

## Why

- **Credential isolation.** AI agents executing shell commands should not have read access to your SSH keys, cloud credentials, or browser data.
- **Clean HOME.** Each workspace gets a fresh `$HOME` with no inherited dotfiles or environment.
- **Persistent per-workspace identity.** The same project always maps to the same sandbox user, so installed tools, caches, and configuration survive across sessions.

This is not a container. It is UNIX-native isolation: separate user, separate HOME, ACL-scoped workspace, clean environment.

---

## How it works

```
~/work/foo                       workspace path
    │
    ▼  canonicalize + blake2s
bal_f81d4f                       deterministic sandbox identity
    │
    ▼  useradd / dscl
sandbox UNIX user                created once, reused forever
    │
    ▼
/home/bal_f81d4f/                isolated HOME (no host dotfiles)
    └── .bal/
        ├── workspace -> /Users/.../work/foo     symlink
        ├── session.json
        └── logs/
    │
    ▼  setfacl / chmod +a
ACL grants sandbox user rwx on the workspace only
    │
    ▼
sudo -u bal_f81d4f HOME=/home/bal_f81d4f claude
```

The sandbox is the primary object. Agents are attached to sandboxes; they do not own them.

---

## Installation

```bash
pip install bal-sbx
```

System requirements:

| Platform | Required |
|---|---|
| Linux   | `sudo`, `acl` package (provides `setfacl`/`getfacl`) |
| macOS   | `sudo`, built-in ACL support (`chmod +a`) |

Python 3.11 or newer.

---

## CLI usage

```bash
# Probe what this host supports
bal-sbx capabilities

# Create a sandbox for the current directory
bal-sbx sandbox create

# List known sandboxes
bal-sbx sandbox list

# Run something inside the sandbox (workspace = cwd by default)
bal-sbx exec -- claude

# Run unsandboxed (explicit opt-out, visible in output)
bal-sbx exec --unsafe -- claude

# Enter the sandbox interactively
bal-sbx sandbox cd

# Set a persistent sandbox-scoped env var
bal-sbx sandbox env ANTHROPIC_BASE_URL http://localhost:11434

# Repair broken symlinks, ACLs, missing HOME
bal-sbx sandbox repair

# Remove stale sandboxes (workspace deleted, orphaned user, …)
bal-sbx sandbox cleanup --dry-run
```

`--workspace PATH` overrides cwd inference on any command.

---

## Python module usage

```python
from bal_sbx import SandboxManager, SandboxMode

manager = SandboxManager()

# Cheap, no side effects
identity = manager.resolve("/Users/me/work/foo")
print(identity.id, identity.user, identity.home)

# Creates user / HOME / symlink / ACL if missing
sandbox = manager.get_or_create("/Users/me/work/foo")

# Sandboxed launcher — replaces the current process
launcher = manager.launcher("/Users/me/work/foo", mode=SandboxMode.SAFE)
launcher.exec_replace(["claude"], env_overrides={"API_TIMEOUT_MS": "3000000"})

# Or fork + wait for scripting / tests
exit_code = launcher.run(["claude", "--version"])

# Explicit unsafe — no sandbox, no isolation
unsafe = manager.unsafe("/Users/me/work/foo")
unsafe.exec_replace(["claude"])
```

The `errors` submodule exposes the exceptions consumers should catch:

```python
from bal_sbx import errors

try:
    manager.get_or_create(workspace)
except errors.PrivilegeDenied:
    ...
except errors.PlatformUnsupported:
    ...
```

---

## Integration with bal

[`bal`](../bal) currently calls `os.execvp` directly from its backends. To sandbox, replace the agent-exec call site with a `SandboxManager` launcher:

```python
# in bal's backend.exec_agent(agent, model):
from bal_sbx import SandboxManager, SandboxMode

mode = SandboxMode.UNSAFE if args.unsafe else SandboxMode.SAFE
launcher = SandboxManager().launcher(os.getcwd(), mode=mode)
launcher.exec_replace([agent, *agent_args], env_overrides=env)
```

`bal-sbx` does not import or modify `bal`. The integration above is a sketch for when `bal` adopts the library.

---

## Security model

What is isolated:

- Filesystem reads/writes outside the workspace and the sandbox HOME.
- Inherited environment variables (a configurable denylist is stripped before exec).
- Shell history and dotfiles from the host user.

What is **not** isolated by this MVP:

- Network access (Phase 4 will add policies).
- Kernel-level resources, capabilities, namespaces (use Docker/bubblewrap/nsjail for that — Phase 3+).
- The workspace itself: the agent has full read/write inside it. The sandbox does not protect you from a malicious agent damaging your own project files.

Treat `bal-sbx` as **credential isolation**, not as a hostile-code containment system.

---

## Platform support

| Platform | User provisioner | ACL backend | Status |
|---|---|---|---|
| Linux (Ubuntu/Debian) | `useradd` / `userdel`     | `setfacl`  | Supported |
| Linux (Fedora/Arch)   | `useradd` / `userdel`     | `setfacl`  | Supported |
| macOS 14+             | `dscl`                    | `chmod +a` | Supported |
| Windows               | —                         | —          | Not planned |

---

## Configuration

Global settings (`~/.bal/sbx.toml`):

```toml
[privilege]
mode = "cached"          # "cached" (default) or "per_operation"

[env]
denylist = [             # stripped before exec
    "AWS_ACCESS_KEY_ID",
    "GITHUB_TOKEN",
    "SSH_AUTH_SOCK",
]

[registry]
path = "~/.bal/sandboxes.json"
```

Per-workspace settings (`.bal/config.json` inside the workspace):

```json
{
  "env": { "MODEL": "gpt-4" }
}
```

Precedence: CLI flag > workspace config > global settings > built-in defaults.

---

## Development

```bash
git clone https://github.com/<you>/bal-sbx
cd bal-sbx
pip install -e ".[dev]"
pytest
```

Style and design rules follow `bal`'s [`coding_philosophy.md`](../bal/docs/coding_philosophy.md) and [`coding_guide.md`](../bal/docs/coding_guide.md):

- PEP 8, line length 120, 20–30 line functions.
- OOP with SOLID; no global state; no single-caller wrappers.
- Tests assert on outcomes, not on which mock was called.
- Prefer the standard library; new dependencies require explicit justification.

Unit tests mock the system layer (`UserProvisioner`, `AclManager`, `PrivilegeBroker`) — `pytest` never invokes real `sudo`.

---

## Roadmap

See [`dev_roadmap/plan.md`](dev_roadmap/plan.md) for the 12-step implementation plan. Phases 1 and 2 from the strategy doc are in scope; Docker backend, network policies, and stronger isolation backends are future work.

---

## License

MIT — see [LICENSE](LICENSE).
