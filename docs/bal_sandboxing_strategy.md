# bal Sandboxing Strategy

## Overview

`bal` should provide secure-by-default execution for AI coding agents.

The default experience:

```bash
cd my-project
bal claude
```

should automatically:
- launch the agent inside a persistent sandbox,
- isolate the agent from the user's real HOME,
- expose only the current workspace,
- preserve sandbox state between sessions.

Unsafe execution must be explicit:

```bash
bal claude --unsafe
```

In unsafe mode, the agent runs directly as the current user without sandboxing.

---

# Design Goals

## 1. Secure by Default

Sandboxing is enabled automatically unless explicitly disabled.

The user should never need to think about sandbox setup.

---

## 2. Persistent Per-Workspace Sandboxes

Each workspace maps to a stable sandbox identity.

Running:

```bash
cd my-project
bal claude
```

multiple times should always reuse:
- the same sandbox user,
- the same isolated HOME,
- the same permissions,
- the same future settings/configuration.

Sandboxes are tied to workspace identity, not process lifetime.

---

## 3. Minimal UNIX-Native Isolation

The implementation should use:
- Linux/macOS users,
- filesystem permissions,
- ACLs,
- symlinks,
- isolated HOME directories.

Avoid heavyweight container systems for the MVP.

---

## 4. Explicit Workspace Access

The agent should only see files explicitly exposed to it.

The sandbox should NOT have access to:
- ~/.ssh
- ~/.aws
- ~/.config
- shell history
- browser credentials
- arbitrary files in the user's HOME

---

# Sandbox Model

## Workspace Identity

A deterministic sandbox ID is derived from the workspace path.

Example:

```text
~/work/foo
→ bal_a1b2c3
```

Recommended implementation:
- canonicalize workspace path,
- hash the path,
- truncate hash for readability.

Possible format:

```text
bal_<hash>
```

Example:

```text
bal_f81d4f
```

---

# Sandbox User

Each workspace gets a dedicated system user.

Example:

```text
bal_f81d4f
```

The user persists across sessions.

---

# Sandbox HOME Structure

Example:

```text
/home/bal_f81d4f/
    .bal/
        workspace -> /actual/project/path
        session.json
        logs/
```

The sandbox HOME must contain:
- no inherited dotfiles,
- no SSH keys,
- no credentials,
- no shell history,
- no environment configuration from the host user.

---

# Workspace Exposure

The current workspace is exposed via symlink:

```text
/home/bal_f81d4f/.bal/workspace
    -> /real/project/path
```

The agent operates through this path.

---

# Filesystem Permissions

Access is granted using ACLs.

Example:

```bash
setfacl -Rm u:bal_f81d4f:rwx /workspace
setfacl -dRm u:bal_f81d4f:rwx /workspace
```

Requirements:
- sandbox user can fully operate inside the workspace,
- sandbox user cannot access unrelated directories,
- ACLs should be repairable.

---

# Agent Launch

Example:

```bash
sudo -u bal_f81d4f \
    HOME=/home/bal_f81d4f \
    claude
```

No user environment variables should be inherited.

Recommended:
- clean environment,
- explicit HOME,
- minimal PATH.

---

# Unsafe Mode

Explicit opt-out:

```bash
bal claude --unsafe
```

Behavior:
- run directly as current user,
- no sandbox,
- no isolation,
- no ACL handling.

This mode should be visually obvious in output/UI.

---

# Sandbox Registry

`bal` should maintain a persistent sandbox registry.

Suggested location:

```text
~/.bal/sandboxes.json
```

Example:

```json
{
  "bal_f81d4f": {
    "workspace": "/Users/aleksei/work/foo",
    "created_at": "2026-05-23T12:00:00Z",
    "last_used_at": "2026-05-23T13:15:00Z",
    "agent": "claude"
  }
}
```

---

# Sandbox Commands

## List Sandboxes

```bash
bal sandbox list
```

Shows:
- sandbox user,
- workspace path,
- last used time,
- status.

---

## Repair Sandboxes

```bash
bal sandbox repair
```

Repairs:
- missing symlink,
- broken ACLs,
- missing HOME directories,
- stale metadata.

---

## Cleanup Stale Sandboxes

```bash
bal sandbox cleanup
```

Removes sandboxes where:
- workspace no longer exists,
- symlink is broken,
- user is orphaned,
- metadata is invalid.

Cleanup should:
- remove ACLs,
- remove HOME,
- delete sandbox user,
- remove registry entry.

---

# Stale Sandbox Detection

A sandbox is considered stale if:
- workspace path does not exist,
- symlink target is missing,
- registry entry is invalid,
- user exists without HOME,
- HOME exists without user.

Optional future improvement:
- validate git remote fingerprint,
- validate workspace inode,
- detect repo replacement.

---

# UX Expectations

## Default

```bash
bal claude
```

Always sandboxed.

---

## Explicit Unsafe Mode

```bash
bal claude --unsafe
```

Always unsandboxed.

---

## Clear Visibility

`bal` should clearly show execution mode.

Example:

```text
BAL SANDBOX: bal_f81d4f
WORKSPACE: ~/work/foo
MODE: sandboxed
```

Unsafe example:

```text
MODE: UNSAFE
```

---

# Root Privileges

Sandbox creation requires privileged operations:
- user creation,
- ACL management,
- ownership management.

Recommended approach:
- request sudo when needed,
- avoid setuid binaries,
- avoid background daemons for MVP.

Example:

```bash
sudo bal claude
```

or:

```bash
bal claude
# prompts for sudo when sandbox must be created/repaired
```

---

# Future Extensions

## Optional Persistent Sandbox Settings

Per-workspace config:

```text
.bal/config.json
```

Potential settings:
- allowed directories,
- environment variables,
- network access,
- mounted paths,
- agent preferences.

---

## Stronger Isolation

Future optional sandbox backends:
- bubblewrap,
- nsjail,
- podman,
- rootless docker.

Potential CLI:

```bash
bal claude --sandbox=bwrap
```

---

# Recommended MVP Implementation Order

## Phase 1 — Core Sandbox

- deterministic sandbox ID generation,
- sandbox registry,
- sandbox user creation,
- isolated HOME creation,
- workspace symlink,
- ACL management,
- launch agent as sandbox user,
- `--unsafe` support.

---

## Phase 2 — Maintenance Commands

- `bal sandbox list`
- `bal sandbox repair`
- `bal sandbox cleanup`
- stale detection.

---

## Phase 3 — Reliability

- signal handling,
- crash recovery,
- ACL rollback,
- corrupted registry recovery.

---

## Phase 4 — Extended Isolation

- clean environment execution,
- optional network restrictions,
- alternative sandbox backends,
- configurable mounts,
- per-workspace policy files.

---

# Philosophy

`bal` should feel like:

```text
persistent isolated AI workspaces
```

not merely:
- a launcher,
- a process wrapper,
- a CLI convenience tool.

The sandbox model should:
- be automatic,
- predictable,
- persistent,
- inspectable,
- UNIX-native,
- developer-friendly.


---

# Revised Sandbox Lifecycle Model

The sandbox system is NOT primarily a process launcher feature.

It is a persistent workspace/runtime management system.

Sandbox creation can happen:
- automatically during agent launch,
- manually through explicit sandbox commands.

Agent launch and sandbox management are separate concerns.

---

# Default Behavior

## Automatic Sandbox Creation

Running:

```bash
bal claude
```

should:

1. resolve the current workspace,
2. locate existing sandbox,
3. create a default sandbox if none exists,
4. launch the agent inside it.

Default sandbox type:

```text
user
```

Equivalent conceptual flow:

```bash
bal sandbox --create --sandbox-type user
bal claude
```

but automatic and transparent.

---

# Explicit Sandbox Creation

Users must also be able to create/manage sandboxes manually.

Example:

```bash
bal sandbox --create --sandbox-type docker
```

This creates the sandbox WITHOUT launching an agent.

The user may want to:
- inspect it,
- install dependencies,
- prepare runtime state,
- configure tooling,
- enter the sandbox manually.

---

# Sandbox Types

Initial conceptual types:

## User Sandbox

```bash
bal claude
```

or:

```bash
bal sandbox --create --sandbox-type user
```

Characteristics:
- isolated UNIX user,
- isolated HOME,
- ACL workspace access,
- lightweight,
- default option.

---

## Docker Sandbox

```bash
bal sandbox --create --sandbox-type docker
```

Potential future behavior:
- containerized execution,
- isolated filesystem,
- isolated networking,
- portable runtime environments.

---

# Sandbox Management Commands

## Explicit Workspace Path

```bash
bal sandbox --path "/path/to/project"
```

Allows:
- creating sandboxes without cd,
- inspecting external workspaces,
- preparing environments remotely.

---

## Environment Variables

Example:

```bash
bal sandbox --venv "KEY" "VALUE"
```

Purpose:
- persistent sandbox-scoped environment variables,
- runtime configuration,
- toolchain setup,
- API configuration.

These variables belong to the sandbox, not the host user.

---

## Enter Sandbox Shell

Example:

```bash
bal sandbox --cd
```

Purpose:
- enter sandbox interactively,
- inspect filesystem,
- install dependencies,
- run tools manually,
- debug runtime state.

Conceptually similar to:

```bash
docker exec -it ...
```

or:

```bash
nix develop
```

but for persistent AI workspaces.

Possible behavior:

```bash
sudo -u bal_f81d4f bash
```

with:
- sandbox HOME,
- workspace mounted,
- sandbox environment loaded.

---

# Separation of Concerns

The architecture should clearly separate:

## 1. Sandbox Runtime Management

Responsible for:
- sandbox creation,
- workspace mapping,
- HOME management,
- ACL management,
- environment persistence,
- runtime state,
- dependency installation.

CLI namespace:

```bash
bal sandbox ...
```

---

## 2. Agent Launching

Responsible for:
- launching Claude/Codex/OpenCode/etc,
- attaching to sandbox,
- backend/model integration.

CLI examples:

```bash
bal claude
bal codex
bal opencode
```

Agent launchers consume sandbox state but do not own it.

---

# Recommended Mental Model

The system should feel like:

```text
persistent isolated developer environments for AI agents
```

NOT:

```text
temporary wrapped subprocesses
```

The sandbox is the primary object.

Agents are attached to sandboxes.

---

# Revised MVP Priority

## Phase 1

- persistent sandbox registry,
- deterministic workspace mapping,
- user sandbox implementation,
- automatic sandbox creation,
- isolated HOME,
- ACL workspace access,
- `bal sandbox --cd`,
- `bal claude --unsafe`.

---

## Phase 2

- sandbox environment variables,
- persistent runtime config,
- repair/cleanup commands,
- stale detection.

---

## Phase 3

- Docker sandbox backend,
- runtime provisioning,
- dependency/bootstrap hooks,
- reusable language runtimes.

---

## Phase 4

- network policies,
- stronger isolation,
- advanced runtime orchestration.
