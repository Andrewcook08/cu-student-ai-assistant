"""Tests for HTML escaping of the ``name`` field in RegisterRequest — SYN-036.

Tests the pydantic model directly (no HTTP, no database) so the validation
logic is exercised in isolation.  The ``validate_name`` field validator on
``RegisterRequest`` must call ``html.escape()`` before returning the value,
preventing stored-XSS via the user's display name.
"""

from __future__ import annotations

from course_search_api.routes.auth import RegisterRequest


def test_register_name_with_html_is_escaped() -> None:
    """HTML special characters in ``name`` must be escaped by the field validator.

    Constructing a RegisterRequest with a name containing an XSS payload must
    store the html-escaped form, not the raw payload.  No DB or HTTP layer is
    involved — the validator runs purely at model construction time.
    """
    payload = "<script>alert('xss')</script>"
    req = RegisterRequest(
        email="user@colorado.edu",
        password="SecurePass1234!",
        name=payload,
    )
    assert req.name == "&lt;script&gt;alert(&#x27;xss&#x27;)&lt;/script&gt;", (
        f"Expected html-escaped name, got {req.name!r}"
    )
