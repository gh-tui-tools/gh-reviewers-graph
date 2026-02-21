# tests/test_cli.py
import pytest

from conftest import reviewers


def test_parse_args_basic():
    args = reviewers.parse_args(["mdn/content"])
    assert args.owner == "mdn"
    assert args.name == "content"
    assert args.output == "./repos"
    assert args.refresh is False


def test_parse_args_rejects_bad_repo():
    with pytest.raises(SystemExit):
        reviewers.parse_args(["badformat"])


def test_parse_args_top_default():
    args = reviewers.parse_args(["mdn/content"])
    assert args.top == 100


def test_parse_args_top_custom():
    args = reviewers.parse_args(["--top", "20", "mdn/content"])
    assert args.top == 20


def test_exclude_default():
    """--exclude defaults to empty string."""
    args = reviewers.parse_args(["owner/repo"])
    assert args.exclude == ""


def test_exclude_parsing():
    """--exclude accepts comma-separated logins."""
    args = reviewers.parse_args(["owner/repo", "--exclude", "bot1,bot2"])
    assert args.exclude == "bot1,bot2"
