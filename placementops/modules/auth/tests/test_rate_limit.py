# @forgeplan-node: auth-module
"""
Tests for POST /api/v1/auth/login rate limiting.

AC3: 10 attempts/minute per IP → 429 on the 11th request.
     429 response must include Retry-After header.
"""
# @forgeplan-spec: AC3

import time
from unittest.mock import MagicMock, patch

import pytest

from placementops.modules.auth.rate_limiter import (
    RATE_LIMIT_MAX,
    RATE_LIMIT_WINDOW,
    _login_attempts,
    check_rate_limit,
    get_client_ip,
    reset_rate_limiter,
)


# ── Unit tests for rate_limiter.py ────────────────────────────────────────────

def test_check_rate_limit_allows_up_to_max():
    """First RATE_LIMIT_MAX attempts from an IP succeed without raising."""
    reset_rate_limiter()
    ip = "192.168.1.1"
    for _ in range(RATE_LIMIT_MAX):
        check_rate_limit(ip)  # Should not raise
    assert len(_login_attempts[ip]) == RATE_LIMIT_MAX


def test_check_rate_limit_raises_429_on_11th():
    """
    AC3: 11th request from the same IP raises HTTP 429 with Retry-After header.
    """
    # @forgeplan-spec: AC3
    from fastapi import HTTPException

    reset_rate_limiter()
    ip = "10.0.0.1"
    for _ in range(RATE_LIMIT_MAX):
        check_rate_limit(ip)

    with pytest.raises(HTTPException) as exc_info:
        check_rate_limit(ip)

    assert exc_info.value.status_code == 429
    assert "Retry-After" in exc_info.value.headers
    assert exc_info.value.headers["Retry-After"] == str(RATE_LIMIT_WINDOW)


def test_rate_limit_sliding_window_evicts_old_entries():
    """Requests older than RATE_LIMIT_WINDOW are evicted before the count check."""
    from collections import deque

    reset_rate_limiter()
    ip = "172.16.0.1"

    # Inject 10 timestamps that are just past the window
    old_time = time.time() - RATE_LIMIT_WINDOW - 1
    _login_attempts[ip] = deque([old_time] * RATE_LIMIT_MAX)

    # All 10 old attempts should be evicted → no rate limit breach
    check_rate_limit(ip)  # Should not raise


def test_rate_limit_different_ips_independent():
    """Rate limit counters are per-IP — different IPs do not share state."""
    from fastapi import HTTPException

    reset_rate_limiter()
    ip_a = "1.2.3.4"
    ip_b = "5.6.7.8"

    for _ in range(RATE_LIMIT_MAX):
        check_rate_limit(ip_a)

    # ip_b has zero attempts — should not be limited
    check_rate_limit(ip_b)  # Should not raise

    # ip_a is now at max — 11th raises
    with pytest.raises(HTTPException) as exc_info:
        check_rate_limit(ip_a)
    assert exc_info.value.status_code == 429


def test_get_client_ip_prefers_x_forwarded_for():
    """get_client_ip() should return the first IP from X-Forwarded-For."""
    from fastapi import Request
    from unittest.mock import MagicMock

    mock_request = MagicMock(spec=Request)
    mock_request.headers = {"X-Forwarded-For": "203.0.113.1, 198.51.100.1"}
    mock_request.client = MagicMock()
    mock_request.client.host = "127.0.0.1"  # trusted proxy — X-Forwarded-For is honoured

    ip = get_client_ip(mock_request)
    assert ip == "203.0.113.1"


def test_get_client_ip_falls_back_to_remote_addr():
    """get_client_ip() falls back to request.client.host when no X-Forwarded-For."""
    from fastapi import Request

    mock_request = MagicMock(spec=Request)
    mock_request.headers = {}
    mock_request.client = MagicMock()
    mock_request.client.host = "192.168.0.5"

    ip = get_client_ip(mock_request)
    assert ip == "192.168.0.5"


# ── Integration: HTTP-level rate limit test ───────────────────────────────────

@pytest.mark.asyncio
async def test_rate_limit_11th_request_returns_429(async_client, base_user):
    """
    AC3 integration: Send 10 login requests (all fail with 401 due to mocked Supabase),
    then the 11th from the same IP returns HTTP 429 with Retry-After header.
    """
    # @forgeplan-spec: AC3
    with patch("placementops.modules.auth.service._get_supabase_client") as mock_factory:
        mock_supabase = MagicMock()
        mock_supabase.auth.sign_in_with_password.side_effect = Exception(
            "Invalid login credentials"
        )
        mock_factory.return_value = mock_supabase

        # Send 10 requests — each returns 401 (wrong password) but rate limit
        # advances on each attempt
        for i in range(10):
            resp = await async_client.post(
                "/api/v1/auth/login",
                json={"email": "user@test.com", "password": "wrong"},
                headers={"X-Forwarded-For": "203.0.113.99"},
            )
            # First 10 should be 401 (rate limit not yet breached)
            assert resp.status_code == 401, (
                f"Request {i+1} expected 401, got {resp.status_code}"
            )

        # 11th request — must be 429
        resp = await async_client.post(
            "/api/v1/auth/login",
            json={"email": "user@test.com", "password": "wrong"},
            headers={"X-Forwarded-For": "203.0.113.99"},
        )

    assert resp.status_code == 429, f"Expected 429, got {resp.status_code}: {resp.text}"
    assert "Retry-After" in resp.headers
    assert resp.headers["Retry-After"] == "60"


@pytest.mark.asyncio
async def test_rate_limit_does_not_block_different_ips(async_client, base_user):
    """
    AC3: Rate limit is per-IP. Exhausting one IP does not block another.
    """
    # @forgeplan-spec: AC3
    with patch("placementops.modules.auth.service._get_supabase_client") as mock_factory:
        mock_supabase = MagicMock()
        mock_supabase.auth.sign_in_with_password.side_effect = Exception("Invalid credentials")
        mock_factory.return_value = mock_supabase

        # Exhaust IP A
        for _ in range(10):
            await async_client.post(
                "/api/v1/auth/login",
                json={"email": "u@test.com", "password": "w"},
                headers={"X-Forwarded-For": "1.1.1.1"},
            )

        # IP B should still get 401 (not 429)
        resp_b = await async_client.post(
            "/api/v1/auth/login",
            json={"email": "u@test.com", "password": "w"},
            headers={"X-Forwarded-For": "2.2.2.2"},
        )

    assert resp_b.status_code == 401, f"Expected 401 for IP B, got {resp_b.status_code}"
