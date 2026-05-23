from datetime import datetime

from bal_sbx.core.metadata import SandboxMetadata


def _sample() -> SandboxMetadata:
    return SandboxMetadata(
        workspace="/Users/me/proj",
        created_at="2026-01-02T03:04:05+00:00",
        last_used_at="2026-01-02T03:04:05+00:00",
        agent="claude",
    )


def test_to_dict_round_trip():
    meta = _sample()
    restored = SandboxMetadata.from_dict(meta.to_dict())
    assert restored == meta


def test_to_dict_round_trip_without_agent():
    meta = SandboxMetadata(
        workspace="/p",
        created_at="2026-01-02T03:04:05+00:00",
        last_used_at="2026-01-02T03:04:05+00:00",
    )
    restored = SandboxMetadata.from_dict(meta.to_dict())
    assert restored == meta
    assert restored.agent is None


def test_to_dict_keys():
    meta = _sample()
    assert set(meta.to_dict()) == {"workspace", "created_at", "last_used_at", "agent"}


def test_timestamps_are_parseable_iso8601():
    meta = _sample()
    datetime.fromisoformat(meta.created_at)
    datetime.fromisoformat(meta.last_used_at)
