# @forgeplan-node: auth-module
"""
Sliding-window rate limiter for POST /api/v1/auth/login.

Enforces 10 attempts per minute per IP address (X-Forwarded-For preferred,
falls back to direct connection remote_addr).

State is in-process (single-instance only — known limitation documented in
spec failure_modes). This module does NOT share state with any other counter.
"""
# @forgeplan-spec: AC3
# @forgeplan-decision: D-auth-3-rate-limiter-module-state -- In-process defaultdict(deque) per spec. Why: spec explicitly describes in-memory sliding window; distributed state is a non-goal for Phase 1

import os
from collections import defaultdict, deque
import time

from fastapi import HTTPException, Request, status

# ── Constants ────────────────────────────────────────────────────────────────

RATE_LIMIT_WINDOW: int = 60   # seconds
RATE_LIMIT_MAX: int = 10      # max attempts per window

# F11: Only trust X-Forwarded-For when the direct connection is from this host
_TRUSTED_PROXY_HOST: str = os.environ.get("TRUSTED_PROXY_HOST", "127.0.0.1")

# F12: Cap the number of tracked IPs to prevent unbounded memory growth
_MAX_TRACKED_IPS: int = 10_000
_EVICT_COUNT: int = 1_000

# Module-level state — NOT shared with any other rate limiter
_login_attempts: dict[str, deque] = defaultdict(deque)


# ── Public API ────────────────────────────────────────────────────────────────

def get_client_ip(request: Request) -> str:
    """
    Extract the client IP for rate-limit keying.

    Only trusts X-Forwarded-For when the direct connection originates from
    the configured trusted proxy host (TRUSTED_PROXY_HOST env var, default
    127.0.0.1). Falls back to request.client.host for all other callers,
    preventing header-spoofing rate-limit bypass (F11).
    """
    # F11: Only honour X-Forwarded-For from a known proxy
    if request.client and request.client.host == _TRUSTED_PROXY_HOST:
        forwarded_for = request.headers.get("X-Forwarded-For", "")
        if forwarded_for:
            return forwarded_for.split(",")[0].strip()
    if request.client:
        return request.client.host
    return "unknown"


def check_rate_limit(ip: str) -> None:
    """
    Enforce the sliding-window rate limit for a given IP.

    Removes attempts older than RATE_LIMIT_WINDOW seconds, then checks
    whether the remaining count meets or exceeds RATE_LIMIT_MAX.

    Raises HTTP 429 with Retry-After: 60 on breach (AC3).
    On success, records the current attempt timestamp.

    F12: If the tracked-IP dict exceeds _MAX_TRACKED_IPS entries, the
    _EVICT_COUNT least-recently-active entries are pruned to bound memory use.
    """
    # @forgeplan-spec: AC3
    now = time.time()
    attempts = _login_attempts[ip]

    # Evict expired attempts (sliding window)
    while attempts and attempts[0] < now - RATE_LIMIT_WINDOW:
        attempts.popleft()

    # F12: Prune empty entries for the current IP immediately
    if not attempts and ip in _login_attempts:
        del _login_attempts[ip]
        attempts = _login_attempts[ip]

    if len(attempts) >= RATE_LIMIT_MAX:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many login attempts. Please wait before retrying.",
            headers={"Retry-After": str(RATE_LIMIT_WINDOW)},
        )

    # Record this attempt
    attempts.append(now)

    # F12: Evict least-recently-active entries when the dict grows too large
    if len(_login_attempts) > _MAX_TRACKED_IPS:
        # Sort by the most-recent timestamp in each deque (smallest = oldest activity)
        oldest_keys = sorted(
            _login_attempts.keys(),
            key=lambda k: _login_attempts[k][-1] if _login_attempts[k] else 0,
        )[:_EVICT_COUNT]
        for key in oldest_keys:
            del _login_attempts[key]


def reset_rate_limiter() -> None:
    """
    Clear all rate-limit state.

    Exposed for use in test teardown only — not part of the production API.
    """
    _login_attempts.clear()
