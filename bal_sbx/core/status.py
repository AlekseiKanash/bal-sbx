"""Sandbox lifecycle/health status values."""

from enum import Enum


class SandboxStatus(str, Enum):
    OK = "ok"
    MISSING_USER = "missing_user"
    MISSING_HOME = "missing_home"
    BROKEN_SYMLINK = "broken_symlink"
    MISSING_WORKSPACE = "missing_workspace"
    DANGLING_ACL = "dangling_acl"
    ORPHAN_HOME = "orphan_home"
    INVALID_METADATA = "invalid_metadata"
