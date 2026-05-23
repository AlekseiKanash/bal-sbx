"""Launcher protocol and concrete implementations.

`AgentLauncher` is a structural `typing.Protocol`; concrete launchers
(`SandboxedLauncher`, `DirectLauncher`) match it via duck typing rather
than inheritance.

SandboxedLauncher argv shape::

    ["sudo", "-u", <user>, "-H", "env", "-i", *KEY=VAL pairs, *cmd]

The redundant `env -i` after `sudo` is intentional. `sudo` policy can leak
a subset of host env even with `-H`; the explicit `env -i` plus an explicit
key/value list after it guarantees a fully scrubbed env regardless of
sudoers configuration.
"""

from __future__ import annotations

import os
import subprocess
import sys
from collections.abc import Iterable, Mapping, Sequence
from typing import NoReturn, Protocol

from bal_sbx.backends.base import Sandbox
from bal_sbx.core.errors import SandboxBroken
from bal_sbx.core.status import SandboxStatus
from bal_sbx.exec.environment import DEFAULT_DENYLIST, build_sandbox_env
from bal_sbx.registry.json_file import JsonFileRegistry
from bal_sbx.system.ops import SystemOps


class AgentLauncher(Protocol):
    def exec_replace(
        self,
        cmd: Sequence[str],
        env_overrides: Mapping[str, str] | None = None,
    ) -> NoReturn: ...

    def run(
        self,
        cmd: Sequence[str],
        env_overrides: Mapping[str, str] | None = None,
    ) -> int: ...


def _env_pairs(env: Mapping[str, str]) -> list[str]:
    return [f"{k}={v}" for k, v in env.items()]


class SandboxedLauncher:
    def __init__(
        self,
        sandbox: Sandbox,
        system_ops: SystemOps,
        registry: JsonFileRegistry,
        denylist: Iterable[str] = DEFAULT_DENYLIST,
    ) -> None:
        self._sandbox = sandbox
        self._system_ops = system_ops
        self._registry = registry
        self._denylist = tuple(denylist)

    def _prepare(
        self,
        env_overrides: Mapping[str, str] | None,
    ) -> list[str]:
        status = self._sandbox.status()
        if status is not SandboxStatus.OK:
            raise SandboxBroken(
                f"refusing to launch into {self._sandbox.identity.id}: "
                f"status is {status.value}"
            )
        self._registry.touch(self._sandbox.identity.id)
        env = build_sandbox_env(
            self._sandbox.identity,
            overrides=env_overrides,
            denylist=self._denylist,
        )
        return _env_pairs(env)

    def _argv(self, env_pairs: list[str], cmd: Sequence[str]) -> list[str]:
        identity = self._sandbox.identity
        return [
            "sudo", "-u", identity.user, "-H",
            "env", "-i", *env_pairs,
            *cmd,
        ]

    def exec_replace(
        self,
        cmd: Sequence[str],
        env_overrides: Mapping[str, str] | None = None,
    ) -> NoReturn:
        env_pairs = self._prepare(env_overrides)
        argv = self._argv(env_pairs, cmd)
        os.execvp("sudo", argv)
        raise RuntimeError("os.execvp returned unexpectedly")

    def run(
        self,
        cmd: Sequence[str],
        env_overrides: Mapping[str, str] | None = None,
    ) -> int:
        env_pairs = self._prepare(env_overrides)
        argv = self._argv(env_pairs, cmd)
        result = subprocess.run(argv, check=False)
        return result.returncode


class DirectLauncher:
    """The --unsafe path. No sandbox, no env scrubbing, no user switch."""

    def __init__(self) -> None:
        pass

    @staticmethod
    def _env(env_overrides: Mapping[str, str] | None) -> dict[str, str]:
        env = dict(os.environ)
        if env_overrides:
            env.update(env_overrides)
        return env

    @staticmethod
    def _announce() -> None:
        # Visibility requirement from the sandboxing strategy doc.
        print("MODE: UNSAFE", file=sys.stderr)

    def exec_replace(
        self,
        cmd: Sequence[str],
        env_overrides: Mapping[str, str] | None = None,
    ) -> NoReturn:
        self._announce()
        env = self._env(env_overrides)
        os.execvpe(cmd[0], list(cmd), env)
        raise RuntimeError("os.execvpe returned unexpectedly")

    def run(
        self,
        cmd: Sequence[str],
        env_overrides: Mapping[str, str] | None = None,
    ) -> int:
        self._announce()
        env = self._env(env_overrides)
        result = subprocess.run(list(cmd), env=env, check=False)
        return result.returncode
