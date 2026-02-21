# tests/test_bot_filter.py
from conftest import reviewers


def test_github_app_bot():
    assert reviewers.is_bot("dependabot[bot]") is True


def test_project_bot():
    assert reviewers.is_bot("ladybird-bot") is True


def test_human_with_bot_substring():
    assert reviewers.is_bot("robotics-fan") is False


def test_case_insensitive():
    assert reviewers.is_bot("BOT") is True


def test_human_login():
    assert reviewers.is_bot("alice") is False


def test_known_bot():
    """KNOWN_BOTS entries are detected as bots."""
    assert reviewers.is_bot("bors-servo") is True
    assert reviewers.is_bot("highfive") is True
    assert reviewers.is_bot("servo-wpt-sync") is True
    assert reviewers.is_bot("webkit-commit-queue") is True
    assert reviewers.is_bot("webkit-early-warning-system") is True


def test_exclude_is_separate_from_is_bot():
    """is_bot does not know about --exclude; that\'s handled at call sites."""
    assert reviewers.is_bot("some-custom-account") is False
