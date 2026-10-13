"""Register / login / logout using Supabase Auth.

The access token is kept in an HttpOnly cookie, so JavaScript never touches it.
"""
from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel

from supabase_client import get_client

TOKEN_COOKIE = "finvia_token"
router = APIRouter(prefix="/api/auth", tags=["auth"])


class Credentials(BaseModel):
    email: str
    password: str


def _is_https(request: Request) -> bool:
    # Behind the AWS load balancer the app sees http, so check the forwarded header.
    return request.headers.get("x-forwarded-proto", request.url.scheme) == "https"


def _set_token(request: Request, response: Response, session) -> None:
    response.set_cookie(
        TOKEN_COOKIE,
        session.access_token,
        max_age=int(getattr(session, "expires_in", None) or 3600),
        httponly=True,
        samesite="lax",
        secure=_is_https(request),
    )


def _message(exc: Exception) -> str:
    return getattr(exc, "message", None) or str(exc) or "Request failed."


def current_user(request: Request) -> dict:
    """Dependency: returns the signed-in user or answers 401."""
    token = request.cookies.get(TOKEN_COOKIE)
    if not token:
        raise HTTPException(401, "Please sign in.")
    try:
        user = get_client().auth.get_user(token).user
    except Exception:
        user = None
    if not user:
        raise HTTPException(401, "Your session has expired. Please sign in again.")
    return {"id": user.id, "email": user.email}


@router.post("/register")
def register(data: Credentials, request: Request, response: Response):
    email = data.email.strip().lower()
    if "@" not in email:
        raise HTTPException(400, "Enter a valid email address.")
    if len(data.password) < 6:
        raise HTTPException(400, "Password must be at least 6 characters.")
    try:
        res = get_client().auth.sign_up({"email": email, "password": data.password})
    except Exception as exc:
        raise HTTPException(400, _message(exc))
    if res.user is None:
        raise HTTPException(400, "Registration failed. Please try again.")

    # If "Confirm email" is ON in Supabase there is no session yet.
    if res.session is None:
        return {"signed_in": False, "message": "Account created. Check your email to confirm it, then sign in."}

    _set_token(request, response, res.session)
    return {"signed_in": True, "user": {"id": res.user.id, "email": res.user.email}}


@router.post("/login")
def login(data: Credentials, request: Request, response: Response):
    try:
        res = get_client().auth.sign_in_with_password(
            {"email": data.email.strip().lower(), "password": data.password}
        )
    except Exception:
        raise HTTPException(401, "Invalid email or password.")
    if res.session is None or res.user is None:
        raise HTTPException(401, "Invalid email or password.")
    _set_token(request, response, res.session)
    return {"signed_in": True, "user": {"id": res.user.id, "email": res.user.email}}


@router.get("/me")
def me(request: Request):
    return {"user": current_user(request)}


@router.post("/logout")
def logout(response: Response):
    response.delete_cookie(TOKEN_COOKIE)
    return {"ok": True}
