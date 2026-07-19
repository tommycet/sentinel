"""Reversible credential revocation adapters for Sentinel.

Stdlib only. The control loop calls quarantine()/release(); the adapter decides
whether to actually revoke (HttpRevoker) or just log (DryRunRevoker).

Safety contract: credential material and secrets must never appear in logs,
error messages, or return values. We log/return only a non-reversible SHA-256
hash of the credential_id for correlation.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import urllib.error
import urllib.request
from abc import ABC, abstractmethod
from typing import Any

log = logging.getLogger("sentinel.revoker")

# ponytail: env names are fixed by spec/deploy contract; do not parametrize.
ENV_URL = "SENTINEL_REVOKE_URL"
ENV_TOKEN = "SENTINEL_REVOKE_TOKEN"
ENV_TIMEOUT = "SENTINEL_REVOKE_TIMEOUT"
DEFAULT_TIMEOUT = 10


def _cred_hash(credential_id: str) -> str:
    """Non-reversible SHA-256 of credential_id, used for logs/returns."""
    return hashlib.sha256(credential_id.encode()).hexdigest()[:16]


def _safe_kwargs(kwargs: dict) -> dict:
    """Allowlist of non-sensitive kwargs safe to log/return."""
    safe_keys = {"incident_id", "alertname", "reason"}
    return {k: v for k, v in kwargs.items() if k in safe_keys}


class _NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Reject cross-origin redirects carrying Authorization (token exfiltration)."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        # Never follow redirects when an Authorization header is set.
        if req.has_header("Authorization"):
            raise urllib.error.HTTPError(
                newurl, code, "redirect blocked (Authorization present)",
                headers, fp
            )
        return super().redirect_request(req, fp, code, msg, headers, newurl)


class Revoker(ABC):
    """Abstract base class: quarantine/release a credential, never raise."""

    @abstractmethod
    def quarantine(self, credential_id: str, **kwargs: Any) -> dict:
        """Quarantine a credential. Never raises; returns status dict."""

    @abstractmethod
    def release(self, credential_id: str, **kwargs: Any) -> dict:
        """Release a quarantined credential. Never raises; returns status dict."""


def _result(success: bool, action: str, credential_id: str, message: str, details=None) -> dict:
    return {
        "success": success,
        "action": action,
        "credential_id_hash": _cred_hash(credential_id),
        "message": message,
        "details": details or {},
    }


class DryRunRevoker(Revoker):
    """Safe default: log intended action, return success without revoking."""

    def quarantine(self, credential_id: str, **kwargs: Any) -> dict:
        ch = _cred_hash(credential_id)
        log.info("dry_run quarantine cred_hash=%s %s", ch, _safe_kwargs(kwargs))
        return _result(
            True,
            "dry_run",
            credential_id,
            f"Dry-run: would quarantine credential {ch}",
            {"safe_context": _safe_kwargs(kwargs)},
        )

    def release(self, credential_id: str, **kwargs: Any) -> dict:
        ch = _cred_hash(credential_id)
        log.info("dry_run release cred_hash=%s %s", ch, _safe_kwargs(kwargs))
        return _result(
            True,
            "dry_run_release",
            credential_id,
            f"Dry-run: would release credential {ch}",
            {"safe_context": _safe_kwargs(kwargs)},
        )


class HttpRevoker(Revoker):
    """POST to an external revocation API. Reads config from env per call."""

    def quarantine(self, credential_id: str, **kwargs: Any) -> dict:
        return self._call("quarantine", credential_id, kwargs)

    def release(self, credential_id: str, **kwargs: Any) -> dict:
        return self._call("release", credential_id, kwargs)

    def _call(self, action: str, credential_id: str, kwargs: dict) -> dict:
        url = os.environ.get(ENV_URL, "")
        if not url:
            return _result(
                False, action, credential_id, f"{ENV_URL} not configured", {}
            )
        token = os.environ.get(ENV_TOKEN, "")
        try:
            timeout = int(os.environ.get(ENV_TIMEOUT, DEFAULT_TIMEOUT))
        except ValueError:
            timeout = DEFAULT_TIMEOUT

        # Invariants last: caller kwargs cannot override action/credential_id.
        payload = {**kwargs, "action": action, "credential_id": credential_id}
        headers = {"Content-Type": "application/json"}
        if token:
            headers["Authorization"] = f"Bearer {token}"

        ch = _cred_hash(credential_id)
        log.info("HTTP %s cred_hash=%s", action, ch)
        try:
            req = urllib.request.Request(
                url,
                data=json.dumps(payload).encode(),
                headers=headers,
                method="POST",
            )
            opener = urllib.request.build_opener(_NoRedirectHandler)
            with opener.open(req, timeout=timeout) as resp:
                status = resp.status
                body = resp.read().decode(errors="replace")
        except TimeoutError:
            return _result(
                False, action, credential_id, f"Request timeout after {timeout}s", {}
            )
        except urllib.error.HTTPError as e:
            return _result(
                False,
                action,
                credential_id,
                f"HTTP {e.code} from revoke endpoint",
                {"status": e.code},
            )
        except urllib.error.URLError as e:
            reason = getattr(e, "reason", "")
            return _result(
                False,
                action,
                credential_id,
                f"Connection error: {reason}",
                {},
            )
        except Exception as e:  # noqa: BLE001 - defensive; never raise to caller
            return _result(
                False,
                action,
                credential_id,
                f"Unexpected error: {type(e).__name__}",
                {},
            )

        if 200 <= status < 300:
            return _result(
                True,
                {"quarantine": "quarantined", "release": "released"}[action],
                credential_id,
                f"HTTP {status}: action '{action}' accepted",
                {"status": status},
            )
        return _result(
            False,
            action,
            credential_id,
            f"HTTP {status} from revoke endpoint",
            {"status": status},
        )


def get_revoker() -> Revoker:
    """Pick the revoker: HttpRevoker if SENTINEL_REVOKE_URL set, else DryRunRevoker."""
    if os.environ.get(ENV_URL):
        return HttpRevoker()
    return DryRunRevoker()
