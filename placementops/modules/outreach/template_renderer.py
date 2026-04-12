# @forgeplan-node: outreach-module
# @forgeplan-spec: AC1
# @forgeplan-spec: AC2
"""
Jinja2 SandboxedEnvironment template renderer for outreach actions.

Security constraints enforced here:
  - ONLY SandboxedEnvironment is used — never bare jinja2.Environment
  - ALLOWED_VARIABLES allowlist is checked BEFORE any rendering
  - Any key outside the allowlist raises HTTP 400 immediately
  - Any Jinja2 security exception during rendering raises HTTP 400

The allowlist check MUST happen before render_template is called.
validate_template_variables() enforces this at the service layer.
"""
# @forgeplan-decision: D-outreach-1-sandboxed-env -- jinja2.sandbox.SandboxedEnvironment for all template rendering. Why: bare Environment allows __class__.__mro__ traversal and other SSTI vectors; SandboxedEnvironment is the only safe choice for user-influenced template content

from __future__ import annotations

from fastapi import HTTPException, status
from jinja2.sandbox import SandboxedEnvironment, SecurityError
from jinja2 import StrictUndefined, UndefinedError, TemplateSyntaxError

# @forgeplan-spec: AC1
# The canonical allowlist of safe template variable names.
# Any key not in this set MUST be rejected with 400 before rendering.
ALLOWED_VARIABLES: frozenset[str] = frozenset({
    "patient_name",
    "facility_name",
    "payer_name",
    "assessment_summary",
    "coordinator_name",
})


class _PlacementSandbox(SandboxedEnvironment):
    """SandboxedEnvironment with additional block on all dunder/private attributes."""

    def is_safe_attribute(self, obj: object, attr: str, value: object) -> bool:
        if attr.startswith("_"):
            return False
        return super().is_safe_attribute(obj, attr, value)


# Single shared SandboxedEnvironment instance — stateless; thread/async-safe.
_SANDBOX_ENV = _PlacementSandbox(
    autoescape=True,  # escape HTML special chars to prevent stored XSS in rendered output
    undefined=StrictUndefined,  # raises UndefinedError on any undeclared variable access
)


# @forgeplan-spec: AC1
def validate_template_variables(variables: dict) -> None:
    """
    Validate that every key in variables is in ALLOWED_VARIABLES.

    Raises HTTP 400 if ANY key is outside the allowlist.
    This MUST be called BEFORE render_template — never pass unknown keys to Jinja2.

    AC1: allowlist-check is the first gate; rendering never occurs with forbidden keys.
    """
    forbidden = set(variables.keys()) - ALLOWED_VARIABLES
    if forbidden:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Template variable(s) not in allowlist: {sorted(forbidden)}. "
                f"Allowed variables are: {sorted(ALLOWED_VARIABLES)}"
            ),
        )


# @forgeplan-spec: AC1
# @forgeplan-spec: AC2
def render_template(template_str: str, variables: dict) -> str:
    """
    Render template_str with the given variables using SandboxedEnvironment.

    Precondition: validate_template_variables(variables) has already been called.
    Raises HTTP 400 on any Jinja2 error (syntax, security, undefined name).

    AC2: SandboxedEnvironment prevents __class__.__mro__ traversal and other SSTI vectors.
    Any expression referencing undeclared names or blocked attributes raises 400.
    """
    try:
        tmpl = _SANDBOX_ENV.from_string(template_str)
        return tmpl.render(**variables)
    except SecurityError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Template contains a disallowed expression: {exc}",
        ) from exc
    except TemplateSyntaxError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Template syntax error: {exc}",
        ) from exc
    except UndefinedError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Template references an undefined variable: {exc}",
        ) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Template rendering failed: {exc}",
        ) from exc
