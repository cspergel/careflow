# Research: Supabase Auth + JWT + FastAPI + RLS + Multi-Tenant + HIPAA

**Date:** 2026-04-10
**Topic:** Supabase JWT forwarding to FastAPI, RLS multi-tenant policies, HIPAA audit logging
**Stack:** Next.js → FastAPI (Python) → PostgreSQL (Supabase), multi-tenant, PHI

---

## Summary

This report covers five research areas:
1. JWT forwarding and validation in FastAPI (not using supabase-py client — pure JWT middleware)
2. Supabase RLS policy patterns for multi-tenant organization_id scoping
3. FastAPI dependency injection for auth + tenant context (request.state pattern)
4. Gotchas: token expiry, service role key, RLS bypass
5. HIPAA audit logging patterns for PostgreSQL/Supabase

---

## 1. JWT Forwarding: Next.js to FastAPI

### Architecture

The recommended pattern for this stack:

```
Next.js client
  └─ signs in via Supabase Auth → receives JWT access token
  └─ includes JWT in Authorization header for every API call:
       Authorization: Bearer <supabase-jwt>

FastAPI backend
  └─ validates JWT locally (no Supabase server roundtrip)
  └─ extracts sub (user_id), email, app_metadata.organization_id
  └─ injects into request.state for downstream handlers
```

Next.js NEVER forwards tokens to the FastAPI backend in a cookie — it sends them as `Authorization: Bearer` headers. FastAPI validates the signature cryptographically and trusts the result.

### Library Choice: PyJWT (not python-jose)

**Use PyJWT.** The FastAPI documentation previously recommended `python-jose`, but that package has been effectively abandoned (last release in 2021, last commit ~2023). FastAPI maintainers merged PR #11589 to update docs to recommend PyJWT.

| Package | Status | License | Weekly Downloads |
|---------|--------|---------|-----------------|
| PyJWT | Actively maintained | MIT | ~25M |
| python-jose | Abandoned | MIT | ~8M (legacy usage) |

```
pip install PyJWT[cryptography]   # cryptography extra needed for RS256/ES256
pip install httpx                  # for JWKS endpoint fetching
```

### Critical: HS256 → ES256 Migration (JWKS)

Supabase has been migrating JWT signing from symmetric HS256 (shared secret) to asymmetric ES256 (JWKS):

- Projects created before October 2025: likely still HS256
- Projects created after October 1, 2025: ES256 by default
- All projects: complete migration expected late 2026

**Check your project:** Dashboard → Settings → Auth → JWT Settings. If you see a "JWT Secret," you're on HS256. If you see a JWKS URL, you're on ES256.

#### HS256 Validation (legacy — current projects created before Oct 2025)

```python
# app/auth/jwt.py
import os
import jwt
from fastapi import Depends, HTTPException, status, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

SUPABASE_JWT_SECRET = os.environ["SUPABASE_JWT_SECRET"]

class SupabaseJWTBearer(HTTPBearer):
    """Extracts and validates Supabase JWT from Authorization header."""

    async def __call__(self, request: Request) -> dict:
        credentials: HTTPAuthorizationCredentials = await super().__call__(request)
        if not credentials or credentials.scheme.lower() != "bearer":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Bearer token required",
                headers={"WWW-Authenticate": "Bearer"},
            )
        return self._decode(credentials.credentials)

    def _decode(self, token: str) -> dict:
        try:
            payload = jwt.decode(
                token,
                SUPABASE_JWT_SECRET,
                algorithms=["HS256"],
                audience="authenticated",
                options={"verify_exp": True},
            )
            return payload
        except jwt.ExpiredSignatureError:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token has expired",
            )
        except jwt.PyJWTError:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid authentication token",
            )
```

#### ES256 Validation (JWKS — new projects, and future state for all)

```python
# app/auth/jwt.py  (JWKS variant)
import os
import jwt
import httpx
from functools import lru_cache
from fastapi import Depends, HTTPException, status, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

SUPABASE_PROJECT_URL = os.environ["SUPABASE_URL"]  # e.g. https://xyz.supabase.co
JWKS_URL = f"{SUPABASE_PROJECT_URL}/auth/v1/.well-known/jwks.json"

# Cache JWKS keys — these rarely change, but refresh if kid not found
_jwks_cache: dict | None = None


async def _get_jwks() -> dict:
    global _jwks_cache
    if _jwks_cache is None:
        async with httpx.AsyncClient() as client:
            resp = await client.get(JWKS_URL)
            resp.raise_for_status()
            _jwks_cache = resp.json()
    return _jwks_cache


async def _get_signing_key(kid: str) -> str:
    global _jwks_cache
    jwks = await _get_jwks()
    for key in jwks.get("keys", []):
        if key["kid"] == kid:
            return jwt.algorithms.ECAlgorithm.from_jwk(key)
    # kid not found — refresh cache once and retry
    _jwks_cache = None
    jwks = await _get_jwks()
    for key in jwks.get("keys", []):
        if key["kid"] == kid:
            return jwt.algorithms.ECAlgorithm.from_jwk(key)
    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unknown JWT key")


async def validate_supabase_token(token: str) -> dict:
    try:
        header = jwt.get_unverified_header(token)
        kid = header.get("kid")
        if not kid:
            raise HTTPException(status_code=401, detail="JWT missing kid header")
        signing_key = await _get_signing_key(kid)
        payload = jwt.decode(
            token,
            signing_key,
            algorithms=["ES256"],
            options={"verify_aud": False},  # Supabase ES256 doesn't set aud consistently
        )
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token has expired")
    except jwt.PyJWTError as e:
        raise HTTPException(status_code=401, detail=f"Invalid token: {e}")
```

**Production note:** Add a proper TTL-based cache (e.g., `cachetools.TTLCache`) instead of the simple module-level variable. JWKS keys are stable but can rotate — the pattern of invalidating the cache when a `kid` is not found handles key rotation gracefully.

---

## 2. FastAPI Dependency Injection: Auth + Tenant Context

### The AuthContext Dataclass

Define a typed container for everything extracted from the JWT:

```python
# app/auth/context.py
from dataclasses import dataclass

@dataclass(frozen=True)
class AuthContext:
    user_id: str           # sub claim (UUID)
    email: str
    organization_id: str   # from app_metadata.organization_id
    role: str              # "authenticated", "service_role", etc.
    raw_claims: dict       # full payload for advanced checks
```

### Dependency Tree

```python
# app/auth/dependencies.py
from fastapi import Depends, Request
from .jwt import SupabaseJWTBearer  # or JWKS variant
from .context import AuthContext

jwt_bearer = SupabaseJWTBearer()

async def get_auth_context(
    claims: dict = Depends(jwt_bearer),
) -> AuthContext:
    """Validates JWT and extracts typed auth context."""
    organization_id = (
        claims.get("app_metadata", {}).get("organization_id")
        or claims.get("user_metadata", {}).get("organization_id")
    )
    if not organization_id:
        raise HTTPException(
            status_code=403,
            detail="No organization_id in token — user must be assigned to an organization",
        )
    return AuthContext(
        user_id=claims["sub"],
        email=claims.get("email", ""),
        organization_id=organization_id,
        role=claims.get("role", "authenticated"),
        raw_claims=claims,
    )

async def require_org_member(
    auth: AuthContext = Depends(get_auth_context),
) -> AuthContext:
    """Alias that makes intent explicit in route signatures."""
    return auth
```

### Usage in Routes

```python
# app/api/placements.py
from fastapi import APIRouter, Depends
from app.auth.dependencies import require_org_member, AuthContext

router = APIRouter(prefix="/placements", tags=["placements"])

@router.get("/")
async def list_placements(auth: AuthContext = Depends(require_org_member)):
    # auth.organization_id is guaranteed non-null here
    # pass to database query or use for RLS enforcement
    ...

@router.get("/{placement_id}")
async def get_placement(
    placement_id: str,
    auth: AuthContext = Depends(require_org_member),
):
    ...
```

### request.state vs Dependency Injection

Two valid approaches:

| Approach | When to use |
|----------|-------------|
| `Depends(get_auth_context)` | Preferred — typed, testable, explicit in function signatures |
| `request.state.auth` | Use when middleware needs to set auth before route resolution (e.g., for rate limiting or logging middleware that runs before DI) |

For middleware that must set state before DI runs:

```python
# app/middleware/auth_middleware.py
from starlette.middleware.base import BaseHTTPMiddleware

class AuthStateMiddleware(BaseHTTPMiddleware):
    """Sets request.state.auth for access in non-DI contexts (e.g., middleware chain)."""

    async def dispatch(self, request: Request, call_next):
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header[7:]
            try:
                claims = jwt.decode(token, ...)  # same validation as above
                request.state.auth = AuthContext(...)
            except Exception:
                request.state.auth = None
        else:
            request.state.auth = None
        return await call_next(request)
```

**Recommendation for this project:** Use `Depends(get_auth_context)` as the primary pattern. Only use `request.state` for cross-cutting middleware (audit logging, rate limiting) that needs auth before DI runs.

---

## 3. Supabase RLS Policy Patterns for Multi-Tenant Orgs

### Prerequisite: organization_id in the JWT

RLS policies that reference `auth.jwt()` need `organization_id` to be present in the JWT claims. There are two approaches:

#### Option A: Custom Access Token Hook (recommended)

Create a PostgreSQL function that runs before every token is issued and injects `organization_id` into `app_metadata`:

```sql
-- Supabase Dashboard → Auth → Hooks → Custom Access Token Hook
CREATE OR REPLACE FUNCTION public.custom_access_token_hook(event jsonb)
RETURNS jsonb
LANGUAGE plpgsql
SECURITY DEFINER
AS $$
DECLARE
    claims jsonb;
    org_id text;
BEGIN
    claims := event -> 'claims';

    -- Look up the user's organization from your memberships table
    SELECT organization_id::text INTO org_id
    FROM public.organization_members
    WHERE user_id = (event ->> 'user_id')::uuid
    LIMIT 1;

    IF org_id IS NOT NULL THEN
        claims := jsonb_set(claims, '{app_metadata, organization_id}', to_jsonb(org_id));
    END IF;

    -- Return modified claims
    RETURN jsonb_set(event, '{claims}', claims);
END;
$$;

-- Grant access for the hook to run
GRANT USAGE ON SCHEMA public TO supabase_auth_admin;
GRANT EXECUTE ON FUNCTION public.custom_access_token_hook TO supabase_auth_admin;
```

Then register this function in: Dashboard → Authentication → Hooks → Custom Access Token Hook.

**Important gotcha:** Custom claims are baked into the JWT at issuance. If you change a user's organization, they will NOT see the new claim until they log out and log back in (or their token is refreshed). For healthcare apps where org changes are rare, this is acceptable. For frequent changes, use Option B.

#### Option B: Database lookup in every policy (no JWT claim needed)

Skip custom claims and do a database lookup in each policy. More flexible, slightly slower.

```sql
-- Helper: check if current user is member of an org
CREATE OR REPLACE FUNCTION public.user_organization_id()
RETURNS uuid
LANGUAGE sql
STABLE
SECURITY DEFINER
AS $$
    SELECT organization_id
    FROM public.organization_members
    WHERE user_id = (SELECT auth.uid())
    LIMIT 1;
$$;
```

### Core Multi-Tenant RLS Patterns

Enable RLS on every table that holds PHI or tenant-scoped data:

```sql
ALTER TABLE public.patients ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.placements ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.placement_notes ENABLE ROW LEVEL SECURITY;
-- ... repeat for all PHI tables
```

#### Pattern 1: Direct JWT claim matching (fast, preferred when using Custom Access Token Hook)

```sql
-- patients table: only members of the same organization can read
CREATE POLICY "org_members_select_patients"
    ON public.patients
    FOR SELECT
    TO authenticated
    USING (
        organization_id::text = (auth.jwt() -> 'app_metadata' ->> 'organization_id')
    );

-- Insert: enforce org membership and prevent cross-org writes
CREATE POLICY "org_members_insert_patients"
    ON public.patients
    FOR INSERT
    TO authenticated
    WITH CHECK (
        organization_id::text = (auth.jwt() -> 'app_metadata' ->> 'organization_id')
    );

-- Update: both USING (can they see the row?) and WITH CHECK (is the new value valid?)
CREATE POLICY "org_members_update_patients"
    ON public.patients
    FOR UPDATE
    TO authenticated
    USING (
        organization_id::text = (auth.jwt() -> 'app_metadata' ->> 'organization_id')
    )
    WITH CHECK (
        -- Prevent changing organization_id (cross-org data move)
        organization_id::text = (auth.jwt() -> 'app_metadata' ->> 'organization_id')
    );

-- Delete: only org members, prevent cross-org deletes
CREATE POLICY "org_members_delete_patients"
    ON public.patients
    FOR DELETE
    TO authenticated
    USING (
        organization_id::text = (auth.jwt() -> 'app_metadata' ->> 'organization_id')
    );
```

#### Pattern 2: Role-based access within the org

```sql
-- Care coordinators can view all org patients; staff see only their assigned ones
CREATE POLICY "role_based_patient_select"
    ON public.patients
    FOR SELECT
    TO authenticated
    USING (
        CASE (auth.jwt() -> 'app_metadata' ->> 'org_role')
            WHEN 'admin'             THEN organization_id::text = (auth.jwt() -> 'app_metadata' ->> 'organization_id')
            WHEN 'care_coordinator'  THEN organization_id::text = (auth.jwt() -> 'app_metadata' ->> 'organization_id')
            WHEN 'staff'             THEN assigned_user_id = (SELECT auth.uid())
            ELSE false
        END
    );
```

#### Pattern 3: Cascaded access via membership table (no JWT custom claim required)

```sql
CREATE POLICY "org_members_select_placements"
    ON public.placements
    FOR SELECT
    TO authenticated
    USING (
        organization_id IN (
            SELECT organization_id
            FROM public.organization_members
            WHERE user_id = (SELECT auth.uid())   -- NOTE: (select auth.uid()) not auth.uid()
        )
    );
```

### Critical Performance Rules

These are measured, not theoretical. Violating them causes severe query regressions:

#### Rule 1: Always wrap auth functions in SELECT (initPlan caching)

```sql
-- SLOW: auth.uid() called once per row — can be 178,000ms on large tables
USING (user_id = auth.uid())

-- FAST: executed once per query as an initPlan, result cached across all rows
USING (user_id = (SELECT auth.uid()))
```

Measured improvement: 178,000ms → 12ms for a function-based check.

#### Rule 2: Index every column referenced in policies

```sql
CREATE INDEX idx_patients_organization_id ON public.patients(organization_id);
CREATE INDEX idx_placements_organization_id ON public.placements(organization_id);
CREATE INDEX idx_placements_assigned_user_id ON public.placements(assigned_user_id);
CREATE INDEX idx_org_members_user_org ON public.organization_members(user_id, organization_id);
```

Measured improvement: 171ms → <0.1ms with index.

#### Rule 3: Get the user's set first, then filter (query direction matters)

```sql
-- SLOW: correlates per row (9,000ms)
USING (
    (SELECT auth.uid()) IN (
        SELECT user_id FROM org_members WHERE org_members.organization_id = placements.organization_id
    )
)

-- FAST: get user's orgs once, then filter (20ms)
USING (
    organization_id IN (
        SELECT organization_id FROM org_members WHERE user_id = (SELECT auth.uid())
    )
)
```

#### Rule 4: Always specify `TO authenticated`

```sql
-- Without TO clause: policy runs for anon users too, wasting resources
CREATE POLICY "..." ON public.patients FOR SELECT USING (...);

-- With TO clause: skips policy evaluation for anonymous requests entirely
CREATE POLICY "..." ON public.patients FOR SELECT TO authenticated USING (...);
```

#### Rule 5: Add explicit filters in your queries too

Even with RLS, the query planner benefits from explicit filters matching your policy:

```python
# FastAPI route — add the filter explicitly even though RLS would filter anyway
result = await db.execute(
    select(Patient).where(Patient.organization_id == auth.organization_id)
)
```

### RLS for SECURITY DEFINER Functions

When you use `SECURITY DEFINER` functions in policies, those functions bypass RLS of the tables they query internally. This is intentional — use it for the membership check helper function, not for anything that should itself be RLS-protected.

```sql
-- CORRECT: membership helper uses SECURITY DEFINER to bypass RLS on org_members
-- (otherwise the policy on org_members would need to evaluate first, causing recursion)
CREATE FUNCTION public.is_org_member(org_id uuid)
RETURNS boolean
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = public
AS $$
    SELECT EXISTS (
        SELECT 1 FROM public.organization_members
        WHERE organization_id = org_id
        AND user_id = (SELECT auth.uid())
    );
$$;
```

### Testing RLS Policies

Test RLS without making API calls — use SQL to simulate a user session:

```sql
-- Simulate an authenticated user with specific org
BEGIN;
SELECT set_config('request.jwt.claims', json_build_object(
    'sub', 'aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee',
    'role', 'authenticated',
    'app_metadata', json_build_object(
        'organization_id', 'ffffffff-0000-1111-2222-333333333333'
    )
)::text, true);
SET LOCAL ROLE authenticated;

-- This should only return rows for the org above
SELECT * FROM public.patients;

-- This should return 0 rows (different org)
SELECT * FROM public.patients WHERE organization_id = 'different-org-uuid';

ROLLBACK;
```

---

## 4. Gotchas

### Gotcha 1: python-jose is abandoned — use PyJWT

As detailed above. FastAPI's own documentation was updated to drop the recommendation. For new projects, use `PyJWT[cryptography]` from day one.

### Gotcha 2: The HS256 → ES256 migration is coming for all projects

New projects (post-October 2025) are already on ES256. Older projects still use HS256 but will be migrated. Build your JWT validation to be algorithm-aware. The JWKS approach works for both if you handle the algorithm parameter correctly.

### Gotcha 3: Stateless JWT validation cannot detect revoked sessions

`jwt.decode()` verifies the signature and expiry claim — it cannot know if the user has logged out server-side. Supabase stores active sessions in `auth.sessions`. A token can be locally valid (good signature, not expired) but the session may have been terminated.

**Mitigation:** For HIPAA, consider checking session validity for sensitive endpoints:

```python
# Option 1: Call Supabase Auth to verify (adds ~100ms latency, guarantees session is live)
# Use sparingly — only for high-sensitivity write operations
async def verify_session_live(access_token: str, supabase_url: str, service_role_key: str):
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{supabase_url}/auth/v1/user",
            headers={
                "Authorization": f"Bearer {access_token}",
                "apikey": service_role_key,
            }
        )
        if resp.status_code != 200:
            raise HTTPException(status_code=401, detail="Session not active")
        return resp.json()

# Option 2: Accept the stateless validation tradeoff and set short JWT expiry (15-30 min)
# Most practical for HIPAA if the JWT expiry is kept short
```

### Gotcha 4: Service role key bypasses ALL RLS — treat it like a root password

The service role key makes requests as `service_role`, which Supabase/PostgREST is configured to bypass RLS for. This is useful for admin operations but catastrophic if misused.

Rules:
- Store in environment variables only, never in code or version control
- Never prefix with `NEXT_PUBLIC_` (would expose to browser)
- In FastAPI, create a separate admin client only for operations that legitimately need RLS bypass (e.g., creating the initial org record during signup)
- Log all service-role operations for HIPAA audit trail

```python
# app/db/clients.py

# User-context client — use for all user-facing operations (respects RLS)
# This is NOT using supabase-py for auth — it's for admin operations only
from supabase import create_client, Client

# Admin client — only for server-initiated operations that legitimately bypass RLS
_admin_client: Client | None = None

def get_admin_client() -> Client:
    global _admin_client
    if _admin_client is None:
        _admin_client = create_client(
            os.environ["SUPABASE_URL"],
            os.environ["SUPABASE_SERVICE_ROLE_KEY"],
        )
    return _admin_client
```

If you're using SQLAlchemy/asyncpg directly (not supabase-py), connect with the service role Postgres credentials only for explicitly admin-flagged operations.

### Gotcha 5: Token refresh is the client's (Next.js) responsibility

FastAPI is stateless — it validates tokens but does not refresh them. The Next.js frontend uses Supabase's `supabase.auth.getSession()` which automatically refreshes the access token when it's close to expiry. When FastAPI returns 401, Next.js should detect it, refresh the token, and retry.

**Next.js token forwarding pattern:**

```typescript
// lib/api.ts — fetch wrapper that auto-refreshes on 401
export async function apiFetch(path: string, options: RequestInit = {}) {
    const { data: { session } } = await supabase.auth.getSession();
    if (!session) throw new Error("Not authenticated");

    const response = await fetch(`${process.env.NEXT_PUBLIC_API_URL}${path}`, {
        ...options,
        headers: {
            ...options.headers,
            "Authorization": `Bearer ${session.access_token}`,
            "Content-Type": "application/json",
        },
    });

    if (response.status === 401) {
        // Token expired — refresh and retry once
        const { data: { session: newSession } } = await supabase.auth.refreshSession();
        if (!newSession) throw new Error("Session expired — please log in again");

        return fetch(`${process.env.NEXT_PUBLIC_API_URL}${path}`, {
            ...options,
            headers: {
                ...options.headers,
                "Authorization": `Bearer ${newSession.access_token}`,
                "Content-Type": "application/json",
            },
        });
    }

    return response;
}
```

### Gotcha 6: RLS silently returns 0 rows on SELECT/UPDATE/DELETE denial (only INSERT throws)

This is intentional PostgreSQL behavior — RLS denials on reads appear as empty result sets, not 403 errors. This is a security feature (prevents enumeration), but it means:

- A bug in your policy won't throw an obvious error — the route will return empty data
- Test both "can access" AND "cannot access" cases in your test suite
- For UPDATE: if the row is invisible due to RLS, the update silently affects 0 rows

```python
# FastAPI route pattern — check affected rows for writes
async def update_patient(patient_id: str, data: PatientUpdate, auth: AuthContext = Depends(require_org_member)):
    result = await db.execute(
        update(Patient)
        .where(Patient.id == patient_id)
        .where(Patient.organization_id == auth.organization_id)  # explicit + RLS
        .values(**data.dict())
        .returning(Patient.id)
    )
    updated = result.fetchone()
    if not updated:
        # Either doesn't exist or belongs to another org — return 404 (not 403, prevents enumeration)
        raise HTTPException(status_code=404, detail="Patient not found")
    return updated
```

### Gotcha 7: pgbouncer transaction pooling breaks SET LOCAL for RLS

If you use pgbouncer in statement pooling mode (common with Supabase connection pooling on the pooler port), `SET LOCAL` and session config variables do not survive across statements. This means patterns that set `app.current_user_id` via `SET LOCAL` will silently leak or fail.

**Mitigation:**
- Use Supabase's direct connection (port 5432) for connections that rely on session variables
- Or use Supabase's transaction pooler (port 6543) with explicit per-query RLS claims rather than session variables
- The JWT-in-Authorization-header pattern (used by PostgREST/supabase-py) handles this automatically because the JWT is re-validated per request

### Gotcha 8: UPDATE policy requires a corresponding SELECT policy

PostgreSQL requires the user to be able to SELECT a row before they can UPDATE it. If you define an UPDATE policy but no SELECT policy, updates silently fail with 0 rows affected.

```sql
-- WRONG: UPDATE without SELECT — updates silently do nothing
CREATE POLICY "update_placements" ON placements FOR UPDATE TO authenticated USING (...);

-- CORRECT: Explicit SELECT policy exists OR use FOR ALL
CREATE POLICY "all_placements" ON placements FOR ALL TO authenticated USING (...) WITH CHECK (...);
```

---

## 5. HIPAA Audit Logging Patterns

### What Supabase Provides Out of the Box

Supabase (HIPAA tier with BAA) provides:
- `auth.audit_log_entries` table — records all auth events (login, logout, password change, MFA events)
- pgAudit extension — can log DDL changes and optionally SELECT/DML statements
- SOC 2 Type 2 and HIPAA compliance infrastructure at the platform level

What Supabase does NOT provide automatically:
- Application-level PHI access audit logs (who accessed which patient record, when)
- Row-level change history for PHI tables
- Tamper-evident audit trail with cryptographic chaining

You must build these yourself. HIPAA technical safeguards require logging every access to ePHI.

### Layer 1: PostgreSQL Trigger-Based Audit Table

Create an append-only audit log that captures all reads and writes on PHI tables:

```sql
-- Audit log table
CREATE TABLE public.phi_audit_log (
    id          bigserial PRIMARY KEY,
    event_time  timestamptz NOT NULL DEFAULT now(),
    user_id     uuid,                   -- auth.uid() at time of event
    org_id      uuid,                   -- organization_id for scoping
    table_name  text NOT NULL,
    record_id   text NOT NULL,          -- primary key of affected row
    action      text NOT NULL,          -- SELECT, INSERT, UPDATE, DELETE
    old_data    jsonb,                  -- NULL for INSERT/SELECT
    new_data    jsonb,                  -- NULL for DELETE
    changed_columns text[],            -- columns that changed on UPDATE
    client_ip   inet,                   -- from request.headers or pg client_addr
    app_context text                    -- endpoint name, correlation ID
);

-- Prevent anyone (including service_role) from updating or deleting audit records
CREATE RULE no_update_audit AS ON UPDATE TO public.phi_audit_log DO INSTEAD NOTHING;
CREATE RULE no_delete_audit AS ON DELETE TO public.phi_audit_log DO INSTEAD NOTHING;

-- Index for HIPAA reporting queries
CREATE INDEX idx_phi_audit_user_time ON public.phi_audit_log(user_id, event_time);
CREATE INDEX idx_phi_audit_record ON public.phi_audit_log(table_name, record_id);
CREATE INDEX idx_phi_audit_org_time ON public.phi_audit_log(org_id, event_time);
```

Trigger function for DML (INSERT/UPDATE/DELETE) — attach to all PHI tables:

```sql
CREATE OR REPLACE FUNCTION public.phi_audit_trigger()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
    v_old_data    jsonb;
    v_new_data    jsonb;
    v_changed     text[];
    v_record_id   text;
    v_user_id     uuid;
    v_org_id      uuid;
BEGIN
    -- Extract user context from JWT (set by PostgREST or our SET LOCAL)
    v_user_id := (
        current_setting('request.jwt.claims', true)::jsonb ->> 'sub'
    )::uuid;
    v_org_id := (
        current_setting('request.jwt.claims', true)::jsonb
        -> 'app_metadata' ->> 'organization_id'
    )::uuid;

    -- Get record ID from the primary key
    v_record_id := COALESCE(
        (to_jsonb(NEW) ->> 'id'),
        (to_jsonb(OLD) ->> 'id'),
        'unknown'
    );

    IF TG_OP = 'INSERT' THEN
        v_new_data := to_jsonb(NEW);
        v_old_data := NULL;

    ELSIF TG_OP = 'UPDATE' THEN
        v_old_data := to_jsonb(OLD);
        v_new_data := to_jsonb(NEW);
        -- Only track what changed
        SELECT array_agg(key)
        INTO v_changed
        FROM jsonb_each(v_old_data) AS o(key, value)
        WHERE o.value IS DISTINCT FROM v_new_data -> o.key;

    ELSIF TG_OP = 'DELETE' THEN
        v_old_data := to_jsonb(OLD);
        v_new_data := NULL;
    END IF;

    INSERT INTO public.phi_audit_log (
        user_id, org_id, table_name, record_id, action,
        old_data, new_data, changed_columns,
        app_context
    ) VALUES (
        v_user_id, v_org_id, TG_TABLE_NAME, v_record_id, TG_OP,
        v_old_data, v_new_data, v_changed,
        current_setting('app.request_context', true)
    );

    RETURN COALESCE(NEW, OLD);
END;
$$;

-- Attach to PHI tables
CREATE TRIGGER audit_patients
    AFTER INSERT OR UPDATE OR DELETE ON public.patients
    FOR EACH ROW EXECUTE FUNCTION public.phi_audit_trigger();

CREATE TRIGGER audit_placements
    AFTER INSERT OR UPDATE OR DELETE ON public.placements
    FOR EACH ROW EXECUTE FUNCTION public.phi_audit_trigger();

CREATE TRIGGER audit_placement_notes
    AFTER INSERT OR UPDATE OR DELETE ON public.placement_notes
    FOR EACH ROW EXECUTE FUNCTION public.phi_audit_trigger();
```

### Layer 2: FastAPI Application-Level Audit Middleware

The PostgreSQL trigger captures writes automatically. For reads (SELECT), you must log from the application layer because PostgreSQL triggers don't fire on SELECT.

```python
# app/audit/middleware.py
import logging
import json
from datetime import datetime, timezone
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware

# Separate audit logger — send to immutable log storage in production
audit_logger = logging.getLogger("phi_audit")

class PHIAuditMiddleware(BaseHTTPMiddleware):
    """
    Logs all requests to PHI endpoints.
    For HIPAA: captures who accessed what data and when.
    """

    # Routes containing PHI — prefix match
    PHI_ROUTE_PREFIXES = ["/patients", "/placements", "/placement-notes"]

    async def dispatch(self, request: Request, call_next):
        is_phi_route = any(
            request.url.path.startswith(prefix)
            for prefix in self.PHI_ROUTE_PREFIXES
        )

        if not is_phi_route:
            return await call_next(request)

        # Capture auth context if available
        auth = getattr(request.state, "auth", None)

        response = await call_next(request)

        # Log after response so we know the outcome
        audit_logger.info(json.dumps({
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "event_type": "phi_access",
            "user_id": auth.user_id if auth else None,
            "organization_id": auth.organization_id if auth else None,
            "email": auth.email if auth else None,
            "method": request.method,
            "path": request.url.path,
            "query_params": dict(request.query_params),
            "status_code": response.status_code,
            "client_ip": request.client.host if request.client else None,
            # NOTE: never log request/response body here — may contain raw PHI
            # Log record IDs from path params only
            "resource_id": request.path_params.get("patient_id")
                           or request.path_params.get("placement_id"),
        }))

        return response
```

Register the middleware:

```python
# app/main.py
from app.audit.middleware import PHIAuditMiddleware
from app.middleware.auth_middleware import AuthStateMiddleware

app = FastAPI()
# Auth state must come first so PHIAuditMiddleware can read request.state.auth
app.add_middleware(AuthStateMiddleware)
app.add_middleware(PHIAuditMiddleware)
```

### Layer 3: Endpoint-Level Decorator for Fine-Grained Audit

For specific high-sensitivity operations (accessing a patient record, viewing placement notes):

```python
# app/audit/decorator.py
import functools
from fastapi import Request

def phi_audit(action: str):
    """Decorator for endpoints that access PHI — logs with action label."""
    def wrapper(func):
        @functools.wraps(func)
        async def decorator(*args, **kwargs):
            request: Request = kwargs.get("request")
            auth = kwargs.get("auth")  # from Depends(require_org_member)

            try:
                result = await func(*args, **kwargs)
                audit_logger.info(json.dumps({
                    "action": action,
                    "user_id": auth.user_id if auth else None,
                    "org_id": auth.organization_id if auth else None,
                    "status": "success",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }))
                return result
            except Exception as e:
                audit_logger.warning(json.dumps({
                    "action": action,
                    "user_id": auth.user_id if auth else None,
                    "org_id": auth.organization_id if auth else None,
                    "status": "error",
                    "error": str(e),
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }))
                raise
        return decorator
    return wrapper

# Usage
@router.get("/patients/{patient_id}")
@phi_audit(action="VIEW_PATIENT_RECORD")
async def get_patient(
    patient_id: str,
    request: Request,
    auth: AuthContext = Depends(require_org_member),
):
    ...
```

### Layer 4: pgAudit for Database-Level Audit (DDL + Schema Changes)

Enable pgAudit for schema/DDL auditing on Supabase:

```sql
CREATE EXTENSION IF NOT EXISTS pgaudit;

-- Log DDL changes and role changes (schema modifications)
-- This goes in your Supabase SQL editor or migration
ALTER ROLE postgres SET pgaudit.log TO 'ddl, role';
```

**Note on pgAudit SELECT logging:** pgAudit can log SELECT statements (`read` category), but on Supabase's hosted platform, `pgaudit.log_parameter` is disabled to protect pgsodium/Vault secrets. This means parameter values won't be logged. For HIPAA SELECT audit, the application-layer middleware (Layer 2) is more reliable than pgAudit for capturing which specific records were accessed.

**pgAudit limitation for HIPAA:** The trigger-based approach (Layer 1) cannot log SELECT statements. pgAudit CAN log SELECT statements but without parameter binding. The combination of pgAudit (for what queries ran) + FastAPI middleware (for who accessed which record IDs) gives the most complete HIPAA audit trail.

### HIPAA Audit Log Requirements Checklist

HIPAA §164.312(b) requires audit controls that record and examine activity on PHI:

| Requirement | Implementation |
|-------------|----------------|
| User ID logged | JWT sub claim in every audit entry |
| Timestamp | `event_time timestamptz DEFAULT now()` |
| Action type | SELECT/INSERT/UPDATE/DELETE in action column |
| Resource accessed | `record_id` (patient_id, placement_id) |
| Outcome | HTTP status code in middleware log |
| 6-year retention | Archive audit table to immutable storage (S3 + Object Lock) |
| Tamper resistance | RULE-based append-only table + offload to WORM storage |
| Encryption | Supabase AES-256 at rest; TLS 1.3 in transit (both automatic on Supabase HIPAA) |

**Critical: Never log PHI values in the audit trail itself.** Log record IDs, user IDs, and timestamps — not the content of PHI fields. The audit log captures who accessed record `patient-uuid-123`, not the patient's name or diagnosis.

### Production Audit Log Destination

The FastAPI audit logger should write to a separate, immutable destination. Do NOT keep audit logs only in PostgreSQL (can be dropped). Recommended pipeline:

```
FastAPI audit_logger
    → stdout/structured JSON
    → AWS CloudWatch Logs (or equivalent)
    → CloudWatch Log Group with 6-year retention + immutability enabled

PostgreSQL phi_audit_log table
    → pg_logical replication
    → S3 with Object Lock (WORM) for tamper-evident long-term storage
```

---

## 6. Recommended Packages

### Package License Report

| Package | License | Downloads/wk | Last Published | Status |
|---------|---------|-------------|----------------|--------|
| PyJWT | MIT | ~25M | 2025-07 | APPROVED |
| httpx | BSD-3-Clause | ~18M | 2025-10 | APPROVED |
| python-jose | MIT | ~8M | 2021-09 | WARNING — abandoned, last release 2021 |
| cachetools | MIT | ~50M | 2025-03 | APPROVED (for JWKS cache TTL) |

**Flagged:** `python-jose` — while the license is MIT (not a legal issue), the package is functionally abandoned. Any new CVEs would not receive patches. For a HIPAA project, using unmaintained cryptographic libraries is an audit finding risk.

**Recommended install:**
```
pip install "PyJWT[cryptography]" httpx cachetools
```

---

## 7. Reference Architecture Summary

The pattern used by production multi-tenant Supabase apps (Makerkit, LockIn, various SaaS starters) converges on:

```
auth layer
  ├─ Supabase Auth: handles signup, login, MFA, session management
  ├─ Custom Access Token Hook: injects organization_id into JWT at issuance
  └─ FastAPI: validates JWT, never calls Supabase auth server per-request

database layer
  ├─ RLS enabled on ALL PHI tables
  ├─ Policies reference auth.jwt() -> 'app_metadata' ->> 'organization_id'
  ├─ (select auth.uid()) wrapper on all auth function calls in policies
  ├─ Indexes on every column referenced in policies
  └─ SECURITY DEFINER helpers for 3+ table membership checks

audit layer
  ├─ PostgreSQL triggers on PHI tables (INSERT/UPDATE/DELETE)
  ├─ FastAPI middleware for PHI route access logging (SELECT coverage)
  ├─ pgAudit for DDL/schema change logging
  └─ Offload to immutable external storage (S3 Object Lock or CloudWatch)

fastapi patterns
  ├─ HTTPBearer → jwt.decode() → AuthContext dataclass → Depends()
  ├─ request.state.auth for middleware-level access (audit, rate limiting)
  ├─ Admin client (service_role) isolated to signup/admin flows only
  └─ Explicit org filter in every query + RLS as defense-in-depth
```

---

## 8. Research Gaps

- **JWKS caching strategy with production concurrency:** The simple module-level cache used in examples is not thread/process-safe under gunicorn with multiple workers. A Redis-based shared JWKS cache or a TTLCache with proper locking is needed for multi-worker deployments. No definitive FastAPI example found for this.
- **pgAudit SELECT logging with Supabase:** The limitation around `pgaudit.log_parameter` being disabled on Supabase HIPAA projects was found, but no workaround or Supabase roadmap item was identified. The application-layer middleware is the current best alternative.
- **Contradiction found:** Some sources recommend storing `organization_id` in `user_metadata` (which users can modify), while Supabase documentation explicitly states `user_metadata` is user-editable and unsuitable for authorization. The correct location is `app_metadata` (admin-only write). Always use `app_metadata` for anything used in RLS or authorization.
- **asyncpg + SET LOCAL for RLS:** The pattern of setting `request.jwt.claims` via `SET LOCAL` within a transaction (for RLS when using asyncpg directly, not PostgREST) is well-documented for Rails and Node, but FastAPI + asyncpg + SQLAlchemy examples are sparse. The recommended approach for this project is to use PostgREST (via supabase-py) for operations that rely on JWT-based RLS, and direct asyncpg only for admin operations using the service role.
- **Custom Access Token Hook organizational change latency:** No source confirmed exact token refresh timing — the claim that users need to log out to pick up org changes is based on general JWT semantics (claim is baked into the token). Verify this against Supabase's token refresh behavior in testing.

---

*Research completed 2026-04-10. Sources include Supabase official docs, FastAPI GitHub discussions, makerkit.dev production patterns, and community implementations.*
