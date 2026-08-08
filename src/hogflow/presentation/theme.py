"""Presentation-only design tokens for the HogFlow industrial desktop HMI."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class OperatorMode(str, Enum):
    """Truthful presentation context derived from the configured source."""

    VALIDATION_BUILD = "VALIDATION BUILD"
    VALIDATION_MODE = "VALIDATION MODE"
    LIVE_MODE = "LIVE MODE"


class SemanticTone(str, Enum):
    """Accessible status intent; labels remain mandatory alongside color."""

    SUCCESS = "success"
    WARNING = "warning"
    CRITICAL = "critical"
    INFORMATION = "information"
    INACTIVE = "inactive"
    NEUTRAL = "neutral"


@dataclass(frozen=True, slots=True)
class HmiColors:
    """Dark industrial palette with restrained semantic accents."""

    background: str = "#07111F"
    surface: str = "#0B1726"
    panel: str = "#101F31"
    panel_elevated: str = "#14263A"
    preview_background: str = "#02070D"
    border: str = "#294159"
    border_active: str = "#2D8CFF"
    text_primary: str = "#F4F8FC"
    text_secondary: str = "#A8B7C7"
    text_muted: str = "#708196"
    accent: str = "#2D8CFF"
    accent_hover: str = "#4CA4FF"
    success: str = "#2ECF88"
    warning: str = "#F0B84B"
    critical: str = "#F05A67"
    information: str = "#45A3FF"
    inactive: str = "#667587"
    focus: str = "#8EC5FF"


@dataclass(frozen=True, slots=True)
class HmiTypography:
    """System-font hierarchy suitable for long-running operator use."""

    family: str = "Segoe UI"
    brand_size: int = 18
    section_size: int = 10
    metric_size: int = 11
    body_size: int = 9
    micro_size: int = 8
    live_count_size: int = 34

    def font(self, size: int, weight: str = "normal") -> tuple[str, int, str]:
        """Return a Tk-compatible system font tuple without external assets."""

        return (self.family, size, weight)


@dataclass(frozen=True, slots=True)
class HmiSpacing:
    """Compact 4/8-based spacing scale for dense industrial dashboards."""

    xsmall: int = 2
    small: int = 4
    medium: int = 8
    large: int = 12


@dataclass(frozen=True, slots=True)
class HmiTheme:
    """Complete immutable visual vocabulary for the Tkinter presentation."""

    colors: HmiColors = HmiColors()
    typography: HmiTypography = HmiTypography()
    spacing: HmiSpacing = HmiSpacing()

    def tone_color(self, tone: SemanticTone) -> str:
        """Resolve one semantic tone to a palette color."""

        if tone is SemanticTone.SUCCESS:
            return self.colors.success
        if tone is SemanticTone.WARNING:
            return self.colors.warning
        if tone is SemanticTone.CRITICAL:
            return self.colors.critical
        if tone is SemanticTone.INFORMATION:
            return self.colors.information
        if tone is SemanticTone.INACTIVE:
            return self.colors.inactive
        return self.colors.text_secondary


HMI_THEME = HmiTheme()


def operator_mode_for_source_type(source_type: str | None) -> OperatorMode:
    """Map safe source provenance to the approved operator-mode language."""

    if source_type == "file":
        return OperatorMode.VALIDATION_MODE
    if source_type in {"usb", "rtsp"}:
        return OperatorMode.LIVE_MODE
    return OperatorMode.VALIDATION_BUILD


def semantic_tone_for_status(status: str) -> SemanticTone:
    """Conservatively map a human-readable snapshot state to visual intent."""

    normalized = status.strip().lower()
    if any(
        token in normalized
        for token in ("failed", "failure", "error", "critical", "unavailable", "disconnected")
    ):
        return SemanticTone.CRITICAL
    if any(
        token in normalized
        for token in (
            "reconnecting",
            "degraded",
            "opening",
            "starting",
            "stopping",
            "exhausted",
            "end of video",
            "warning",
            "attention",
        )
    ):
        return SemanticTone.WARNING
    if any(
        token in normalized
        for token in (
            "running",
            "ready",
            "connected",
            "available",
            "completed",
            "alive",
            "healthy",
        )
    ):
        return SemanticTone.SUCCESS
    if any(token in normalized for token in ("occupied", "active", "selected")):
        return SemanticTone.INFORMATION
    if any(
        token in normalized
        for token in (
            "stopped",
            "closed",
            "idle",
            "waiting",
            "disabled",
            "not configured",
            "planned",
        )
    ):
        return SemanticTone.INACTIVE
    return SemanticTone.NEUTRAL


__all__ = [
    "HMI_THEME",
    "HmiColors",
    "HmiSpacing",
    "HmiTheme",
    "HmiTypography",
    "OperatorMode",
    "SemanticTone",
    "operator_mode_for_source_type",
    "semantic_tone_for_status",
]
