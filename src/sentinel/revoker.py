"""Reversible credential revocation adapters for Sentinel.

Stdlib only. The control loop calls quarantine()/release(); the adapter decides
whether to actually revoke (HttpRevoker) or just log (DryRunRevoker).
"""
from __future__ import annotations

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
        "credential_id": credential_id,
        "message": message,
        "details": details or {},
    }


class DryRunRevoker(Revoker):
    """Safe default: log intended action, return success without revoking."""

    def quarantine(self, credential_id: str, **kwargs: Any) -> dict:
        log.info("dry_run quarantine credential=%s %s", credential_id, kwargs)
        return _result(
            True,
            "dry_run",
            credential_id,
            f"Dry-run: would quarantine credential {credential_id!r}",
            {"kwargs": kwargs},
        )

    def release(self, credential_id: str, **kwargs: Any) -> dict:
        log.info("dry_run release credential=%s %s", credential_id, kwargs)
        return _result(
            True,
            "dry_run_release",
            credential_id,
            f"Dry-run: would release credential {credential_id!r}",
            {"kwargs": kwargs},
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

        payload = {"action": action, "credential_id": credential_id, **kwargs}
        headers = {"Content-Type": "application/json"}
        if token:
            headers["Authorization"] = f"Bearer {token}"

        log.info("HTTP %s credential=%s url=%s", action, credential_id, url)
        try:
            req = urllib.request.Request(
                url,
                data=json.dumps(payload).encode(),
                headers=headers,
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                status = resp.status
                body = resp.read().decode(errors="replace")
        except TimeoutError:
            return _result(
                False, action, credential_id, f"Request timeout after {timeout}s", {}
            )
        except urllib.error.HTTPError as e:
            # HTTP error: server responded with non-2xx. Use status code + safe
            # excerpt; never echo auth header or body secrets.
            return _result(
                False,
                action,
                credential_id,
                f"HTTP {e.code} from revoke endpoint",
                {"status": e.code},
            )
        except urllib.error.URLError as e:
            reason = getattr(e, "reason", "")
            # urllib wraps OSError reasons; keep only native repr, never secrets
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
