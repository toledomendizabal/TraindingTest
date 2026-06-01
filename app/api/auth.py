"""Authentication API endpoints - Google OAuth2."""
import os
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import RedirectResponse
from app.core.config import settings

router = APIRouter()

# OAuth2 state
_auth_state = {
    "authenticated": False,
    "user_email": None,
    "user_name": None
}


@router.get("/status")
async def get_auth_status():
    """Get current authentication status."""
    return {
        "authenticated": _auth_state["authenticated"],
        "user": {
            "email": _auth_state["user_email"],
            "name": _auth_state["user_name"]
        } if _auth_state["authenticated"] else None
    }


@router.post("/login")
async def login():
    """Initiate Google OAuth2 login."""
    try:
        client_secret_path = os.path.join(settings.CONFIG_DIR, "client_secret.json")

        if not os.path.exists(client_secret_path):
            return {
                "status": "error",
                "message": "client_secret.json not found. Please place it in the config/ directory.",
                "auth_url": None
            }

        from google_auth_oauthlib.flow import Flow

        flow = Flow.from_client_secrets_file(
            client_secret_path,
            scopes=[
                "https://www.googleapis.com/auth/gmail.send",
                "https://www.googleapis.com/auth/userinfo.email",
                "https://www.googleapis.com/auth/userinfo.profile"
            ],
            redirect_uri="http://localhost:8000/api/auth/callback"
        )

        auth_url, _ = flow.authorization_url(prompt="consent")

        return {
            "status": "redirect",
            "auth_url": auth_url,
            "message": "Please complete Google OAuth2 authentication"
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/callback")
async def auth_callback(code: str = None, error: str = None):
    """Handle OAuth2 callback."""
    if error:
        return RedirectResponse(url="/?auth=error")

    try:
        client_secret_path = os.path.join(settings.CONFIG_DIR, "client_secret.json")

        from google_auth_oauthlib.flow import Flow
        from google.oauth2.credentials import Credentials

        flow = Flow.from_client_secrets_file(
            client_secret_path,
            scopes=[
                "https://www.googleapis.com/auth/gmail.send",
                "https://www.googleapis.com/auth/userinfo.email",
                "https://www.googleapis.com/auth/userinfo.profile"
            ],
            redirect_uri="http://localhost:8000/api/auth/callback"
        )

        flow.fetch_token(code=code)
        credentials = flow.credentials

        # Save token
        token_path = os.path.join(settings.CONFIG_DIR, "token.json")
        with open(token_path, "w") as f:
            f.write(credentials.to_json())

        # Get user info
        from googleapiclient.discovery import build
        service = build("oauth2", "v2", credentials=credentials)
        user_info = service.userinfo().get().execute()

        _auth_state["authenticated"] = True
        _auth_state["user_email"] = user_info.get("email", "")
        _auth_state["user_name"] = user_info.get("name", "")

        # Initialize email service
        from app.services.email_service import email_service
        await email_service.initialize()

        return RedirectResponse(url="/?auth=success")

    except Exception as e:
        return RedirectResponse(url=f"/?auth=error&message={str(e)}")


@router.post("/logout")
async def logout():
    """Logout and clear authentication."""
    _auth_state["authenticated"] = False
    _auth_state["user_email"] = None
    _auth_state["user_name"] = None

    token_path = os.path.join(settings.CONFIG_DIR, "token.json")
    if os.path.exists(token_path):
        os.remove(token_path)

    return {"status": "success", "message": "Logged out successfully"}
