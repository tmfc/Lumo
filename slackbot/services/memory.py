"""Integration with the mem0.ai memory service."""
from __future__ import annotations

import logging
from datetime import date
from typing import Any, Dict, Optional

from django.conf import settings

logger = logging.getLogger(__name__)

Mem0Memory: Any
try:  # pragma: no cover - optional dependency
    from mem0 import Memory as Mem0Memory  # type: ignore
except Exception:  # pragma: no cover - mem0 might not be installed under this name
    try:
        from mem0ai import Memory as Mem0Memory  # type: ignore
    except Exception:  # pragma: no cover
        Mem0Memory = None  # type: ignore


class SummaryMemory:
    """Persist generated summaries to mem0 when configured."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        user_id: Optional[str] = None,
        base_url: Optional[str] = None,
    ):
        self.api_key = api_key or getattr(settings, "MEM0_API_KEY", "")
        self.user_id = user_id or getattr(settings, "MEM0_DEFAULT_USER_ID", "lumo-slackbot")
        self.base_url = base_url or getattr(settings, "MEM0_BASE_URL", "")
        self._client = None
        if self.api_key:
            if Mem0Memory is None:
                raise RuntimeError(
                    "mem0ai is not installed. Run `pip install mem0ai` to enable memory support."
                )
            client_kwargs: Dict[str, Any] = {"api_key": self.api_key}
            if self.base_url:
                client_kwargs["base_url"] = self.base_url
            self._client = self._init_client(client_kwargs)

    def _init_client(self, client_kwargs: Dict[str, Any]) -> Any:
        try:
            return Mem0Memory(**client_kwargs)
        except TypeError as exc:
            if "base_url" in client_kwargs:
                base_url = client_kwargs.pop("base_url")
                logger.warning(
                    "mem0 client does not accept base_url=%s; retrying without custom host: %s",
                    base_url,
                    exc,
                )
                return Mem0Memory(**client_kwargs)
            raise

    @property
    def enabled(self) -> bool:
        return self._client is not None

    def remember_summary(
        self,
        *,
        summary_text: str,
        target_type: str,
        target_id: str,
        generated_for: Optional[date] = None,
        model_used: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Any:
        """Store the summary text inside mem0 if configured."""

        if not self._client:
            return None

        default_metadata: Dict[str, Any] = {
            "category": "slack-summary",
            "target_type": target_type,
            "target_id": target_id,
            "model_used": model_used,
            "generated_for": generated_for.isoformat() if generated_for else None,
        }
        payload_metadata = {**(metadata or {}), **default_metadata}
        sanitized_metadata = {k: v for k, v in payload_metadata.items() if v not in (None, "")}

        try:
            return self._client.add(summary_text, metadata=sanitized_metadata, user_id=self.user_id)
        except TypeError:
            payload = {
                "text": summary_text,
                "metadata": sanitized_metadata,
                "user_id": self.user_id,
            }
            try:
                return self._client.add(payload)
            except Exception as exc:  # pragma: no cover - defensive fallback
                logger.warning("mem0 add() failed with payload fallback: %s", exc, exc_info=True)
                return None
        except Exception as exc:  # pragma: no cover - do not crash the request
            logger.warning("Unable to persist summary in mem0: %s", exc, exc_info=True)
            return None
