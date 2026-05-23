"""Tests for the CLI dispatcher."""

from __future__ import annotations

import pytest

from bal_sbx.cli.main import COMMANDS, build_parser, main


def test_main_no_args_exits_nonzero_with_usage(capsys):
    with pytest.raises(SystemExit) as exc:
        main([])
    assert exc.value.code != 0
    err = capsys.readouterr().err
    assert "usage" in err.lower()


def test_main_unknown_command_exits_nonzero():
    with pytest.raises(SystemExit) as exc:
        main(["definitely-not-a-command"])
    assert exc.value.code != 0


def test_commands_table_covers_known_subcommands():
    assert "exec" in COMMANDS
    assert "capabilities" in COMMANDS


def test_parser_registers_sandbox_placeholder_group():
    parser = build_parser()
    # `sandbox` exists but has no subcommands yet; supplying just `sandbox`
    # should fail because subcommand is required.
    with pytest.raises(SystemExit):
        parser.parse_args(["sandbox"])
