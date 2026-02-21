# tests/test_rate_limit.py
"""Tests for rate limit estimation, budget check, and countdown."""

import json
import subprocess
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

from conftest import reviewers


# --- get_rate_limit_info ---


def test_get_rate_limit_info_success():
    """Parses remaining and reset timestamp from gh api output."""
    reset_ts = int(datetime(2024, 6, 15, 14, 32, 0, tzinfo=timezone.utc).timestamp())
    mock_result = MagicMock()
    mock_result.stdout = json.dumps(
        {"remaining": 3421, "limit": 5000, "reset": reset_ts}
    )

    with patch("subprocess.run", return_value=mock_result) as mock_run:
        remaining, reset_dt = reviewers.get_rate_limit_info()

    assert remaining == 3421
    assert reset_dt.year == 2024
    assert reset_dt.month == 6
    assert reset_dt.day == 15
    mock_run.assert_called_once()
    cmd = mock_run.call_args[0][0]
    assert "rate_limit" in cmd


def test_get_rate_limit_info_failure():
    """Returns (None, None) when gh api fails."""
    with patch("subprocess.run", side_effect=subprocess.CalledProcessError(1, "gh")):
        remaining, reset_dt = reviewers.get_rate_limit_info()

    assert remaining is None
    assert reset_dt is None


def test_get_rate_limit_info_bad_json():
    """Returns (None, None) on invalid JSON output."""
    mock_result = MagicMock()
    mock_result.stdout = "not json"

    with patch("subprocess.run", return_value=mock_result):
        remaining, reset_dt = reviewers.get_rate_limit_info()

    assert remaining is None
    assert reset_dt is None


# --- estimate_api_calls ---


def test_estimate_api_calls_small_repo():
    """12 months, 20 reviewers produces a reasonable estimate."""
    result = reviewers.estimate_api_calls(12, 20)
    # Should be roughly: 2 + 12 + ceil(36*2/25) + ceil(20/15) + ceil(480/25) + 12 + ceil(200/25)
    # = 2 + 12 + 3 + 2 + 20 + 12 + 8 = 59
    assert 40 < result < 100


def test_estimate_api_calls_large_repo():
    """155 months, 100 reviewers matches the plan's ~1637 estimate."""
    result = reviewers.estimate_api_calls(155, 100)
    assert 1500 < result < 1800


def test_estimate_api_calls_scales_with_months():
    """More months means more API calls."""
    small = reviewers.estimate_api_calls(12, 50)
    large = reviewers.estimate_api_calls(120, 50)
    assert large > small


# --- estimate_incremental_calls ---


def test_estimate_incremental_calls():
    """Fewer stale months produces fewer calls than full range."""
    full = reviewers.estimate_api_calls(120, 50)
    incremental = reviewers.estimate_incremental_calls(50, 3, 120)
    assert incremental < full


def test_estimate_incremental_calls_scales_with_stale():
    """More stale months means more calls."""
    few = reviewers.estimate_incremental_calls(50, 2, 120)
    many = reviewers.estimate_incremental_calls(50, 20, 120)
    assert many > few


# --- check_rate_limit_budget ---


@patch.object(reviewers, "get_rate_limit_info")
def test_check_rate_limit_budget_sufficient(mock_info, capsys):
    """No warning when budget is sufficient."""
    future = datetime.now(timezone.utc) + timedelta(hours=1)
    mock_info.return_value = (5000, future)

    reviewers.check_rate_limit_budget(200)

    output = capsys.readouterr().out
    assert "Rate limit:" in output
    assert "Estimated API calls:" in output
    assert "Warning" not in output


@patch.object(reviewers, "get_rate_limit_info")
def test_check_rate_limit_budget_insufficient(mock_info, capsys):
    """Warning printed when estimated exceeds remaining."""
    future = datetime.now(timezone.utc) + timedelta(hours=1)
    mock_info.return_value = (100, future)

    reviewers.check_rate_limit_budget(500)

    output = capsys.readouterr().out
    assert "Warning" in output
    assert "exceeds" in output


@patch.object(reviewers, "get_rate_limit_info")
def test_check_rate_limit_budget_unavailable(mock_info, capsys):
    """Prints nothing when rate limit info unavailable."""
    mock_info.return_value = (None, None)

    reviewers.check_rate_limit_budget(500)

    output = capsys.readouterr().out
    assert output == ""


@patch.object(reviewers, "get_rate_limit_info")
def test_check_rate_limit_budget_shows_local_time(mock_info, capsys):
    """Reset time is displayed in local timezone, not UTC."""
    utc_reset = datetime(2024, 6, 15, 5, 56, 0, tzinfo=timezone.utc)
    mock_info.return_value = (4832, utc_reset)

    reviewers.check_rate_limit_budget(200)

    output = capsys.readouterr().out
    expected_time = utc_reset.astimezone().strftime("%H:%M")
    assert f"resets at {expected_time})" in output


# --- _wait_for_rate_limit_reset ---


@patch("time.sleep")
@patch.object(reviewers, "get_rate_limit_info")
@patch.object(reviewers, "datetime")
def test_wait_for_rate_limit_reset_countdown(mock_dt, mock_info, mock_sleep):
    """Sleeps in chunks until the reset time."""
    from datetime import datetime as real_datetime

    now = real_datetime(2024, 6, 15, 14, 0, 0, tzinfo=timezone.utc)
    reset = real_datetime(2024, 6, 15, 14, 0, 30, tzinfo=timezone.utc)

    # datetime.now() called multiple times during countdown
    call_count = [0]

    def fake_now(tz=None):
        call_count[0] += 1
        # First few calls: before reset; later calls: past reset
        if call_count[0] <= 3:
            return now
        return reset + timedelta(seconds=1)

    mock_dt.now.side_effect = fake_now
    mock_dt.fromtimestamp = real_datetime.fromtimestamp
    mock_info.return_value = (0, reset)

    # Clear cached target from prior tests
    reviewers._rate_limit_reset_target = None

    reviewers._wait_for_rate_limit_reset()

    # Should have slept at least once
    assert mock_sleep.call_count >= 1


@patch("time.sleep")
@patch.object(reviewers, "get_rate_limit_info")
def test_wait_for_rate_limit_reset_fallback(mock_info, mock_sleep):
    """Falls back to 60s sleep when info unavailable."""
    mock_info.return_value = (None, None)

    # Clear cached target
    reviewers._rate_limit_reset_target = None

    reviewers._wait_for_rate_limit_reset()

    mock_sleep.assert_called_once_with(60)


@patch("time.sleep")
@patch.object(reviewers, "get_rate_limit_info")
def test_wait_for_rate_limit_reset_too_far(mock_info, mock_sleep):
    """Falls back to 60s sleep when reset is more than 60 minutes away."""
    far_future = datetime.now(timezone.utc) + timedelta(hours=2)
    mock_info.return_value = (0, far_future)

    # Clear cached target
    reviewers._rate_limit_reset_target = None

    reviewers._wait_for_rate_limit_reset()

    mock_sleep.assert_called_once_with(60)


@patch("time.sleep")
@patch.object(reviewers, "get_rate_limit_info")
@patch.object(reviewers, "datetime")
def test_wait_for_rate_limit_reset_reuses_cached_target(mock_dt, mock_info, mock_sleep):
    """Second call reuses cached reset target instead of querying again."""
    from datetime import datetime as real_datetime

    now = real_datetime(2024, 6, 15, 14, 0, 0, tzinfo=timezone.utc)
    reset = real_datetime(2024, 6, 15, 14, 0, 30, tzinfo=timezone.utc)

    call_count = [0]

    def fake_now(tz=None):
        call_count[0] += 1
        if call_count[0] <= 6:
            return now
        return reset + timedelta(seconds=1)

    mock_dt.now.side_effect = fake_now
    mock_dt.fromtimestamp = real_datetime.fromtimestamp
    mock_info.return_value = (0, reset)

    # Clear cached target
    reviewers._rate_limit_reset_target = None

    # First call: queries get_rate_limit_info and sets _rate_limit_reset_target
    reviewers._wait_for_rate_limit_reset()
    assert mock_info.call_count == 1

    # Reset call_count so the second call also sees "now" as before reset
    call_count[0] = 0
    mock_sleep.reset_mock()

    # Second call: reuses cached target, does NOT call get_rate_limit_info again
    reviewers._wait_for_rate_limit_reset()
    assert mock_info.call_count == 1  # still 1, not 2
    assert mock_sleep.call_count >= 1
