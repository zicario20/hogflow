"""Runtime-only camera source protection and safe display helpers."""

from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import urlsplit

from hogflow.core import ConfigurationError
from hogflow.streaming.models import SourceType, StreamIdentity

_RTSP_PATTERN = re.compile(r"(?i)\brtsps?://[^\s]+")
_STREAM_ID_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}")
_SENSITIVE_ID_WORDS = ("credential", "password", "secret", "token")


def sanitized_source_label(source_type: SourceType, stream_id: str) -> str:
    """Return a source label containing only type and opaque stream ID."""

    if not isinstance(source_type, SourceType):
        raise ConfigurationError("Camera source type must be explicit.")
    if (
        not isinstance(stream_id, str)
        or _STREAM_ID_PATTERN.fullmatch(stream_id) is None
        or any(word in stream_id.lower() for word in _SENSITIVE_ID_WORDS)
    ):
        raise ConfigurationError("Stream ID must be a non-sensitive opaque identifier.")
    return f"{source_type.value}-camera:{stream_id}"


class ProtectedSource:
    """Hold a runtime locator while redacting ``str`` and ``repr`` output.

    The raw value is available only through the deliberately named
    :meth:`reveal_for_adapter` method. It must never be logged, serialized,
    included in an exception, or copied into health and statistics models.
    """

    __slots__ = ("_raw_value", "_safe_label", "_source_type")

    def __init__(self, source_type: SourceType, raw_value: str, stream_id: str) -> None:
        if not isinstance(raw_value, str) or not raw_value:
            raise ConfigurationError("Camera source locator must be non-empty text.")
        if source_type is SourceType.RTSP:
            try:
                parsed = urlsplit(raw_value)
            except ValueError:
                raise ConfigurationError("RTSP source must be a valid RTSP URL.") from None
            if parsed.scheme.lower() not in {"rtsp", "rtsps"} or not parsed.hostname:
                raise ConfigurationError("RTSP source must be a valid RTSP URL.")
        elif source_type is SourceType.FILE:
            if not raw_value.strip():
                raise ConfigurationError("Local development source must be non-empty.")
        else:
            raise ConfigurationError("Protected source locators are only for RTSP or file input.")
        self._source_type = source_type
        self._raw_value = raw_value
        self._safe_label = sanitized_source_label(source_type, stream_id)

    @property
    def source_type(self) -> SourceType:
        """Return the explicit non-secret source category."""

        return self._source_type

    @property
    def safe_label(self) -> str:
        """Return the only representation permitted in output."""

        return self._safe_label

    def reveal_for_adapter(self) -> str:
        """Return the runtime locator for an infrastructure adapter only."""

        return self._raw_value

    def __repr__(self) -> str:
        return f"ProtectedSource({self._safe_label!r})"

    def __str__(self) -> str:
        return self._safe_label


def protected_rtsp_source(url: str, stream_id: str) -> ProtectedSource:
    """Validate and protect a runtime RTSP URL."""

    return ProtectedSource(SourceType.RTSP, url, stream_id)


def protected_file_source(path: str | Path, stream_id: str) -> ProtectedSource:
    """Protect a local development path from representations and reports."""

    if not isinstance(path, (str, Path)):
        raise ConfigurationError("Local development source must be a path.")
    return ProtectedSource(SourceType.FILE, str(path), stream_id)


def redact_camera_secrets(text: str) -> str:
    """Remove complete RTSP references from unexpected diagnostic text."""

    if not isinstance(text, str):
        raise ConfigurationError("Diagnostic text must be a string.")
    return _RTSP_PATTERN.sub("rtsp://<redacted>", text)


def identity_for(source_type: SourceType, stream_id: str) -> StreamIdentity:
    """Build an opaque identity that cannot reveal a locator through ``repr``."""

    return StreamIdentity(
        stream_id=stream_id,
        source_type=source_type,
        display_name=sanitized_source_label(source_type, stream_id),
    )


__all__ = [
    "ProtectedSource",
    "identity_for",
    "protected_file_source",
    "protected_rtsp_source",
    "redact_camera_secrets",
    "sanitized_source_label",
]
