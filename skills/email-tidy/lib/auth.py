#!/usr/bin/env python3
"""M365 authentication for Graph API.

Reads config from ~/.claude/m365/.env (TENANT_ID, GRAPH_CLIENT_ID).
Token cache shared with other M365 skills at ~/.claude/m365/.token_cache_skills.json.
"""

import json
import os
import sys
from pathlib import Path

import msal
from dotenv import load_dotenv

M365_DIR = Path.home() / ".claude" / "m365"
TOKEN_CACHE_FILE = M365_DIR / ".token_cache_skills.json"
# Use .default to request all consented scopes for the app registration.
DEFAULT_SCOPES = ["https://graph.microsoft.com/.default"]
GRAPH_ENDPOINT = "https://graph.microsoft.com/v1.0"


def _load_env():
    """Load and validate M365 environment variables."""
    env_file = M365_DIR / ".env"
    if env_file.exists():
        load_dotenv(env_file)

    tenant_id = os.getenv("TENANT_ID")
    client_id = os.getenv("GRAPH_CLIENT_ID")

    if not tenant_id:
        print(json.dumps({"error": "TENANT_ID not found in ~/.claude/m365/.env"}),
              file=sys.stderr)
        sys.exit(1)
    if not client_id:
        print(json.dumps({"error": "GRAPH_CLIENT_ID not found in ~/.claude/m365/.env"}),
              file=sys.stderr)
        sys.exit(1)

    return tenant_id, client_id


def get_token() -> str:
    """Get an access token, using cached token or interactive browser flow."""
    tenant_id, client_id = _load_env()

    cache = msal.SerializableTokenCache()
    if TOKEN_CACHE_FILE.exists():
        cache.deserialize(TOKEN_CACHE_FILE.read_text())

    app = msal.PublicClientApplication(
        client_id,
        authority=f"https://login.microsoftonline.com/{tenant_id}",
        token_cache=cache,
    )

    accounts = app.get_accounts()
    result = None

    if accounts:
        result = app.acquire_token_silent(DEFAULT_SCOPES, account=accounts[0])

    if not result:
        result = app.acquire_token_interactive(scopes=DEFAULT_SCOPES)

    M365_DIR.mkdir(parents=True, exist_ok=True)
    TOKEN_CACHE_FILE.write_text(cache.serialize())

    if "access_token" not in result:
        print(json.dumps({"error": "Authentication failed", "details": result.get("error_description", "")}),
              file=sys.stderr)
        sys.exit(1)

    return result["access_token"]


def get_headers() -> dict:
    """Return headers dict ready for Graph API requests."""
    token = get_token()
    return {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
