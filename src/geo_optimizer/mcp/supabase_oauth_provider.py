"""Supabase Auth adapter for the GEOSITION MCP consent flow."""

from __future__ import annotations

import re
from urllib.parse import urlsplit

import requests


class SupabaseOAuthProvider:
    """Fetch identity and OAuth details directly from a configured Auth server.

    The caller supplies the publicly usable Supabase publishable key and the
    user's Supabase session token, never the service-role key. This adapter
    does not log or persist the session token.
    """

    def __init__(self, project_url, publishable_key, site_origin, *, request=requests.request):
        project = urlsplit(project_url)
        site = urlsplit(site_origin)
        if (
            project.scheme != "https"
            or not project.hostname
            or project.username
            or project.password
            or project.path not in ("", "/")
            or project.query
            or project.fragment
            or site.scheme != "https"
            or not site.hostname
            or site.username
            or site.password
            or site.path not in ("", "/")
            or site.query
            or site.fragment
        ):
            raise ValueError("Supabase project and site origin must be HTTPS origins.")
        if not publishable_key.startswith("sb_publishable_"):
            raise ValueError("A Supabase publishable key is required.")
        self.issuer = project_url.rstrip("/") + "/auth/v1"
        self.site_origin = site_origin.rstrip("/")
        self.publishable_key = publishable_key
        self.request = request

    def _call(self, method, path, token, body=None):
        if not token:
            raise PermissionError("Provider sign-in required.")
        try:
            result = self.request(
                method,
                self.issuer + path,
                headers={
                    "apikey": self.publishable_key,
                    "Authorization": "Bearer " + token,
                    "Origin": self.site_origin,
                },
                json=body,
                timeout=15,
                allow_redirects=False,
            )
        except requests.RequestException as exc:
            raise RuntimeError("The identity provider is unavailable.") from exc
        if result.status_code in (401, 403):
            raise PermissionError("Provider sign-in or authorization is invalid.")
        if result.status_code < 200 or result.status_code >= 300:
            raise ValueError("The provider could not complete the authorization request.")
        try:
            data = result.json()
        except ValueError as exc:
            raise RuntimeError("The identity provider returned an invalid response.") from exc
        if not isinstance(data, dict):
            raise RuntimeError("The identity provider returned an invalid response.")
        return data

    def get_user(self, token):
        """Ask Supabase to validate the session and return its current user."""
        return self._call("GET", "/user", token)

    def sign_in(self, email, password):
        """Authenticate a provider identity without returning its password."""
        if not isinstance(email, str) or not isinstance(password, str) or not email or not password:
            raise ValueError("Enter the email and password for your identity account.")
        try:
            result = self.request(
                "POST",
                self.issuer + "/token?grant_type=password",
                headers={"apikey": self.publishable_key, "Origin": self.site_origin},
                json={"email": email, "password": password},
                timeout=15,
                allow_redirects=False,
            )
        except requests.RequestException as exc:
            raise RuntimeError("The identity provider is unavailable.") from exc
        if result.status_code < 200 or result.status_code >= 300:
            raise PermissionError("Identity sign-in failed. Check your email and password.")
        try:
            data = result.json()
        except ValueError as exc:
            raise RuntimeError("The identity provider returned an invalid response.") from exc
        if not isinstance(data, dict) or not isinstance(data.get("access_token"), str) or not data["access_token"]:
            raise RuntimeError("The identity provider returned an invalid response.")
        return data["access_token"]

    def get_authorization_details(self, token, authorization_id):
        """Fetch the pending OAuth request as the authenticated provider user."""
        return self._call("GET", "/oauth/authorizations/" + self._authorization_id(authorization_id), token)

    @staticmethod
    def _authorization_id(value):
        if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", value):
            raise ValueError("Invalid authorization request.")
        return value

    def decide(self, token, authorization_id, decision):
        """Ask Supabase to approve or deny the pending authorization."""
        if decision not in ("approve", "deny"):
            raise ValueError("Invalid consent decision.")
        return self._call(
            "POST",
            "/oauth/authorizations/" + self._authorization_id(authorization_id) + "/consent",
            token,
            {"action": decision},
        )
