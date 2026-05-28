"""Tests for the CLI dispatcher.

The run-in-sandbox path (single-positional case) is covered in `test_run.py`.
These tests cover the dispatcher's structural invariants and the management
subparser surface.
"""

from __future__ import annotations

import pytest

from bal_sbx.cli.main import COMMANDS, RESERVED, build_parser, main


def test_main_no_args_exits_with_usage_on_stderr(capsys):
    rc = main([])
    assert rc == 2
    err = capsys.readouterr().err
    assert "usage" in err.lower()


def test_main_help_flag_prints_help_to_stdout(capsys):
    rc = main(["--help"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "usage" in out.lower()
    assert "sandbox" in out.lower()


def test_commands_table_covers_management_subcommands():
    assert set(COMMANDS) == {"capabilities", "sandbox", "tools"}


def test_reserved_words_are_the_only_subcommands():
    assert set(RESERVED) == set(COMMANDS)


def test_build_parser_requires_sandbox_subcommand():
    parser = build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(["sandbox"])


def test_build_parser_rejects_removed_exec_subcommand():
    parser = build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(["exec", "--", "echo", "hi"])


def test_build_parser_rejects_removed_sandbox_cd_subcommand():
    parser = build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(["sandbox", "cd"])
