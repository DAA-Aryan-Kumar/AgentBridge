"""Auth endpoints: signup / login / logout.

Signup returns the ONE-TIME recovery code (D5) — the frontend must show it
before moving on. Login on a migrated v1 account upgrades it in place
(pbkdf2 -> scrypt, identity keys provisioned) and, when keys were just
minted, returns that same one-time code.
"""

from __future__ import annotations

from .context import GuiApp

__all__ = ["GET", "POST"]


def signup(app: GuiApp, req) -> dict:
    data = req.data
    return app.signup(
        (data.get("username") or data.get("name") or "").strip().lower(),
        (data.get("display") or "").strip(),
        data.get("password") or "",
    )


def login(app: GuiApp, req) -> dict:
    data = req.data
    return app.login(
        (data.get("username") or data.get("name") or "").strip().lower(),
        data.get("password") or "",
    )


def logout(app: GuiApp, req) -> dict:
    return app.logout()


GET: dict = {}
POST = {
    "/api/mesh/signup": signup,
    "/api/mesh/login": login,
    "/api/mesh/logout": logout,
}
