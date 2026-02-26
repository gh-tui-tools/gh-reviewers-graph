# tests/test_graphql.py
import json
import subprocess
from unittest.mock import patch

import pytest

from conftest import reviewers


def _success(data):
    """Create a CompletedProcess with JSON stdout."""
    return subprocess.CompletedProcess(
        args=["gh"],
        returncode=0,
        stdout=json.dumps(data),
        stderr="",
    )


def _error(stderr):
    """Create a CalledProcessError with given stderr."""
    err = subprocess.CalledProcessError(1, ["gh"])
    err.stderr = stderr
    err.stdout = ""
    return err


@patch.object(reviewers, "get_rate_limit_info", return_value=(None, None))
@patch("time.sleep")
@patch("subprocess.run")
class TestGraphqlRequest:
    def test_success(self, mock_run, mock_sleep, mock_rl):
        mock_run.return_value = _success({"data": {"repository": {"name": "test"}}})
        result = reviewers._graphql_request("query { }", {"owner": "o"})
        assert result == {"repository": {"name": "test"}}
        mock_run.assert_called_once()
        mock_sleep.assert_not_called()

    def test_graphql_error_raises(self, mock_run, mock_sleep, mock_rl):
        mock_run.return_value = _success({"errors": [{"message": "some error"}]})
        with pytest.raises(RuntimeError, match="GraphQL error"):
            reviewers._graphql_request("query { }")

    def test_graphql_error_allow_partial(self, mock_run, mock_sleep, mock_rl):
        mock_run.return_value = _success(
            {
                "errors": [{"message": "partial fail"}],
                "data": {"user": {"login": "alice"}},
            }
        )
        result = reviewers._graphql_request("query { }", allow_partial=True)
        assert result == {"user": {"login": "alice"}}

    def test_os_error_retries(self, mock_run, mock_sleep, mock_rl):
        mock_run.side_effect = [
            OSError("connection refused"),
            OSError("connection refused"),
            _success({"data": {"ok": True}}),
        ]
        result = reviewers._graphql_request("query { }")
        assert result == {"ok": True}
        assert mock_run.call_count == 3
        assert mock_sleep.call_count == 2

    def test_os_error_exhausted(self, mock_run, mock_sleep, mock_rl):
        mock_run.side_effect = OSError("connection refused")
        with pytest.raises(OSError):
            reviewers._graphql_request("query { }")
        assert mock_run.call_count == 6  # initial + 5 retries

    def test_rate_limit_403(self, mock_run, mock_sleep, mock_rl):
        mock_run.side_effect = [
            _error("HTTP 403: rate limit exceeded"),
            _success({"data": {"ok": True}}),
        ]
        result = reviewers._graphql_request("query { }")
        assert result == {"ok": True}
        mock_sleep.assert_any_call(60)

    def test_rate_limit_200_with_error(self, mock_run, mock_sleep, mock_rl):
        mock_run.side_effect = [
            _success({"errors": [{"message": "API rate limit exceeded"}]}),
            _success({"data": {"ok": True}}),
        ]
        result = reviewers._graphql_request("query { }")
        assert result == {"ok": True}

    def test_server_error_retries(self, mock_run, mock_sleep, mock_rl):
        mock_run.side_effect = [
            _error("HTTP 502: Bad Gateway"),
            _success({"data": {"ok": True}}),
        ]
        result = reviewers._graphql_request("query { }")
        assert result == {"ok": True}
        assert mock_run.call_count == 2

    def test_server_error_exhausted(self, mock_run, mock_sleep, mock_rl):
        mock_run.side_effect = _error("HTTP 502: Bad Gateway")
        with pytest.raises(RuntimeError, match="gh api graphql failed"):
            reviewers._graphql_request("query { }")
        assert mock_run.call_count == 6

    def test_network_timeout_retries(self, mock_run, mock_sleep, mock_rl):
        mock_run.side_effect = [
            _error(
                'Post "https://api.github.com/graphql": dial tcp 140.82.112.6:443: i/o timeout'
            ),
            _success({"data": {"ok": True}}),
        ]
        result = reviewers._graphql_request("query { }")
        assert result == {"ok": True}
        assert mock_run.call_count == 2

    def test_network_timeout_exhausted(self, mock_run, mock_sleep, mock_rl):
        mock_run.side_effect = _error(
            'Post "https://api.github.com/graphql": dial tcp 140.82.112.6:443: i/o timeout'
        )
        with pytest.raises(RuntimeError, match="gh api graphql failed"):
            reviewers._graphql_request("query { }")
        assert mock_run.call_count == 6

    def test_proactive_rate_limit_pause(self, mock_run, mock_sleep, mock_rl):
        mock_run.return_value = _success(
            {
                "data": {
                    "rateLimit": {
                        "remaining": 10,
                        "resetAt": "2099-01-01T00:00:00Z",
                    },
                    "ok": True,
                }
            }
        )
        result = reviewers._graphql_request("query { }")
        assert result["ok"] is True
        # Should have called sleep for the proactive pause
        assert mock_sleep.call_count == 1
        # Wait should be positive (reset is far in the future + 5s)
        wait_arg = mock_sleep.call_args[0][0]
        assert wait_arg > 0

    def test_proactive_rate_limit_no_reset_at(self, mock_run, mock_sleep, mock_rl):
        """Proactive pause defaults to 60s when resetAt is empty."""
        mock_run.return_value = _success(
            {
                "data": {
                    "rateLimit": {
                        "remaining": 10,
                        "resetAt": "",
                    },
                    "ok": True,
                }
            }
        )
        result = reviewers._graphql_request("query { }")
        assert result["ok"] is True
        assert mock_sleep.call_count == 1
        mock_sleep.assert_called_with(60)

    def test_rate_limit_no_details(self, mock_run, mock_sleep, mock_rl):
        """403 with rate limit defaults to 60s wait."""
        mock_run.side_effect = [
            _error("HTTP 403: rate limit"),
            _success({"data": {"ok": True}}),
        ]
        result = reviewers._graphql_request("query { }")
        assert result == {"ok": True}
        mock_sleep.assert_any_call(60)

    def test_allow_partial_with_nonzero_exit(self, mock_run, mock_sleep, mock_rl):
        """allow_partial extracts data from stdout even when gh exits non-zero."""
        err = subprocess.CalledProcessError(1, ["gh"])
        err.stderr = "Could not resolve to a User with the login of 'netlify'."
        err.stdout = json.dumps(
            {
                "data": {
                    "u_alice": {
                        "login": "alice",
                        "avatarUrl": "https://a.com/alice.png",
                    }
                },
                "errors": [{"message": "Could not resolve to a User"}],
            }
        )
        mock_run.side_effect = err
        result = reviewers._graphql_request("query { }", allow_partial=True)
        assert result == {
            "u_alice": {"login": "alice", "avatarUrl": "https://a.com/alice.png"}
        }

    def test_allow_partial_with_invalid_stdout(self, mock_run, mock_sleep, mock_rl):
        """allow_partial falls through to error handling if stdout is not valid JSON."""
        err = subprocess.CalledProcessError(1, ["gh"])
        err.stderr = "some unknown error"
        err.stdout = "not valid json"
        mock_run.side_effect = err
        with pytest.raises(RuntimeError, match="gh api graphql failed"):
            reviewers._graphql_request("query { }", allow_partial=True)

    def test_other_error_raises(self, mock_run, mock_sleep, mock_rl):
        """Non-rate-limit, non-transient errors raise RuntimeError."""
        mock_run.side_effect = _error("HTTP 401: Unauthorized")
        with pytest.raises(RuntimeError, match="gh api graphql failed"):
            reviewers._graphql_request("query { }")

    def test_variables_passed_as_flags(self, mock_run, mock_sleep, mock_rl):
        """Variables are passed as -f key=value arguments."""
        mock_run.return_value = _success({"data": {"ok": True}})
        reviewers._graphql_request("query { }", {"owner": "o", "name": "r"})
        cmd = mock_run.call_args[0][0]
        assert "-f" in cmd
        assert "owner=o" in cmd
        assert "name=r" in cmd

    def test_none_variables_skipped(self, mock_run, mock_sleep, mock_rl):
        """None-valued variables are not passed as flags."""
        mock_run.return_value = _success({"data": {"ok": True}})
        reviewers._graphql_request("query { }", {"cursor": None, "owner": "o"})
        cmd = mock_run.call_args[0][0]
        assert "cursor=None" not in " ".join(cmd)
        assert "owner=o" in cmd
