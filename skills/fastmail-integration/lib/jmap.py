#!/usr/bin/env python3
"""Fastmail JMAP client.

Authenticates with a Fastmail API token (Bearer auth) and provides thin
helpers over the JMAP protocol (RFC 8620 core + RFC 8621 mail).

Two auth methods are supported (Fastmail's JMAP endpoint accepts either):

  1. Bearer API token  -> FASTMAIL_API_TOKEN=fmu1-...
       Create in Fastmail: Settings -> Privacy & Security -> Manage API tokens.
       Scope: Mail (read + write).

  2. Basic auth with an app password -> FASTMAIL_USER + FASTMAIL_APP_PASSWORD
       Create in Fastmail: Settings -> Privacy & Security -> App passwords.
       The app password must allow JMAP access (an "IMAP only" password is
       rejected by the JMAP endpoint). This lets the skill share the same
       credential as the invoice-harvester app.

If FASTMAIL_API_TOKEN is set it takes precedence; otherwise the user/app-password
pair is used. Config lives in ~/.claude/fastmail/.env. This skill only ever
creates drafts, so read + write Mail is sufficient.
"""

import json
import os
import sys
from pathlib import Path

import requests
from dotenv import load_dotenv

FASTMAIL_DIR = Path.home() / ".claude" / "fastmail"
ENV_FILE = FASTMAIL_DIR / ".env"
SESSION_URL = "https://api.fastmail.com/jmap/session"

# JMAP capability URNs
CORE = "urn:ietf:params:jmap:core"
MAIL = "urn:ietf:params:jmap:mail"
SUBMISSION = "urn:ietf:params:jmap:submission"

TIMEOUT = 30


def die(message, **extra):
    """Print a JSON error to stderr and exit non-zero."""
    payload = {"error": message}
    payload.update(extra)
    print(json.dumps(payload), file=sys.stderr)
    sys.exit(1)


def load_credentials():
    """Load Fastmail credentials from env or ~/.claude/fastmail/.env.

    Returns ("bearer", token) or ("basic", (user, app_password)). Bearer token
    wins if both are present. Exits with a helpful error if neither is set.
    """
    if ENV_FILE.exists():
        load_dotenv(ENV_FILE)

    token = os.getenv("FASTMAIL_API_TOKEN")
    if token:
        return "bearer", token

    user = os.getenv("FASTMAIL_USER")
    app_password = os.getenv("FASTMAIL_APP_PASSWORD")
    if user and app_password:
        return "basic", (user, app_password)

    die(
        "No Fastmail credentials found. Add ONE of these to "
        "~/.claude/fastmail/.env: (a) FASTMAIL_API_TOKEN (Settings -> Privacy "
        "& Security -> Manage API tokens), or (b) FASTMAIL_USER + "
        "FASTMAIL_APP_PASSWORD (an app password that allows JMAP access).",
        config_path=str(ENV_FILE),
    )


class JmapClient:
    """Minimal JMAP client scoped to a single Fastmail account."""

    def __init__(self, credentials=None):
        scheme, secret = credentials or load_credentials()
        self.auth_scheme = scheme
        self._session = requests.Session()
        self._session.headers.update(
            {"Content-Type": "application/json", "Accept": "application/json"}
        )
        if scheme == "bearer":
            self._session.headers["Authorization"] = f"Bearer {secret}"
        else:  # basic auth with (user, app_password)
            self._session.auth = secret
        self.api_url = None
        self.account_id = None
        self._connect()

    def _connect(self):
        """Fetch the JMAP session resource to discover apiUrl + accountId."""
        try:
            resp = self._session.get(SESSION_URL, timeout=TIMEOUT)
        except requests.RequestException as exc:
            die("Could not reach Fastmail JMAP session endpoint", details=str(exc))

        if resp.status_code == 401:
            hint = (
                "the app password may be scoped IMAP-only — it must allow JMAP"
                if self.auth_scheme == "basic"
                else "check FASTMAIL_API_TOKEN"
            )
            die(f"Fastmail rejected the credentials (401); {hint}.",
                auth_scheme=self.auth_scheme)
        if resp.status_code != 200:
            die(
                "Unexpected status from JMAP session endpoint",
                status=resp.status_code,
                body=resp.text[:500],
            )

        data = resp.json()
        self.api_url = data["apiUrl"]
        primary = data.get("primaryAccounts", {})
        self.account_id = primary.get(MAIL)
        if not self.account_id:
            # Fall back to the first account that has the mail capability.
            for acc_id, acc in data.get("accounts", {}).items():
                if MAIL in acc.get("accountCapabilities", {}):
                    self.account_id = acc_id
                    break
        if not self.account_id:
            die("No mail-capable account found for this token.")
        self.session_data = data

    def call(self, method_calls, using=(CORE, MAIL)):
        """POST a batch of JMAP method calls and return the parsed response.

        method_calls: list of [method, args, call_id]. The account_id is added
        to each args dict automatically if not already present.
        """
        prepared = []
        for name, args, call_id in method_calls:
            args = dict(args)
            args.setdefault("accountId", self.account_id)
            prepared.append([name, args, call_id])

        body = {"using": list(using), "methodCalls": prepared}
        try:
            resp = self._session.post(self.api_url, json=body, timeout=TIMEOUT)
        except requests.RequestException as exc:
            die("JMAP request failed", details=str(exc))

        if resp.status_code != 200:
            die("JMAP request returned non-200", status=resp.status_code,
                body=resp.text[:1000])

        data = resp.json()
        # Surface method-level errors rather than silently returning them.
        for entry in data.get("methodResponses", []):
            if entry[0] == "error":
                die("JMAP method error", method_error=entry[1])
        return data

    def first_result(self, response):
        """Return the args dict of the first method response."""
        return response["methodResponses"][0][1]

    # --- convenience helpers ---

    def get_mailboxes(self):
        """Return the list of all mailboxes (folders)."""
        resp = self.call([["Mailbox/get", {"ids": None}, "0"]])
        return self.first_result(resp)["list"]

    def mailbox_by_role(self, role: str):
        """Find a mailbox by its JMAP role (e.g. 'drafts', 'inbox', 'sent')."""
        for mb in self.get_mailboxes():
            if mb.get("role") == role:
                return mb
        return None

    def mailbox_by_name(self, name: str):
        """Find a mailbox by display name (case-insensitive)."""
        target = name.strip().lower()
        for mb in self.get_mailboxes():
            if mb.get("name", "").lower() == target:
                return mb
        return None
