"""Sanitized local reports for one autonomous counting test."""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from pathlib import Path
from tempfile import NamedTemporaryFile
from threading import Event, Thread
from time import sleep

from hogflow.calibration.orchestration import AutonomousDemoConfiguration, AutonomousDemoResult

_NON_VERIFIED = "AUTONOMOUS ESTIMATE — NOT INDEPENDENTLY VERIFIED"


@dataclass(frozen=True, slots=True)
class AutonomousReportPaths:
    """Paths written under an explicitly local ignored report root."""

    json_path: Path
    markdown_path: Path


@dataclass(frozen=True, slots=True)
class RuntimeResourceSnapshot:
    """Sampled process/device resources; unavailable values remain ``None``."""

    peak_ram_mb: float | None
    peak_vram_mb: float | None
    measurement: str


class RuntimeResourceSampler:
    """Bounded low-rate sampler used only around local benchmark runs."""

    def __init__(self, sample_interval_seconds: float = 0.10) -> None:
        if sample_interval_seconds <= 0:
            raise ValueError("Resource sampler interval must be positive.")
        self._interval = float(sample_interval_seconds)
        self._stop = Event()
        self._thread: Thread | None = None
        self._peak_ram = 0.0
        self._peak_vram = 0.0
        self._has_ram = False
        self._has_vram = False

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            raise RuntimeError("Resource sampler is already running.")
        self._stop.clear()
        self._thread = Thread(target=self._sample, name="hogflow-resource-sampler", daemon=True)
        self._thread.start()

    def stop(self) -> RuntimeResourceSnapshot:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=max(1.0, self._interval * 4))
        if self._has_ram and self._has_vram:
            measurement = "sampled_process_rss_and_device_vram"
        elif self._has_ram:
            measurement = "sampled_process_rss_only"
        else:
            measurement = "unavailable"
        return RuntimeResourceSnapshot(
            peak_ram_mb=round(self._peak_ram, 3) if self._has_ram else None,
            peak_vram_mb=round(self._peak_vram, 3) if self._has_vram else None,
            measurement=measurement,
        )

    def _sample(self) -> None:
        try:
            import psutil

            process = psutil.Process()
        except ImportError:
            process = None
        nvml = None
        device = None
        try:
            import pynvml

            pynvml.nvmlInit()
            nvml = pynvml
            device = pynvml.nvmlDeviceGetHandleByIndex(0)
        except Exception:
            nvml = None
        try:
            while not self._stop.is_set():
                if process is not None:
                    try:
                        self._peak_ram = max(self._peak_ram, process.memory_info().rss / (1024**2))
                        self._has_ram = True
                    except Exception:
                        pass
                if nvml is not None and device is not None:
                    try:
                        self._peak_vram = max(
                            self._peak_vram,
                            nvml.nvmlDeviceGetMemoryInfo(device).used / (1024**2),
                        )
                        self._has_vram = True
                    except Exception:
                        pass
                sleep(self._interval)
        finally:
            if nvml is not None:
                try:
                    nvml.nvmlShutdown()
                except Exception:
                    pass


def _sha256(path: Path) -> str | None:
    try:
        digest = hashlib.sha256()
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()
    except OSError:
        return None


def _line_payload(result: AutonomousDemoResult) -> dict[str, object] | None:
    line = result.calibration.selected_line
    if line is None:
        return None
    return {
        "start": {"x": line.start.x, "y": line.start.y},
        "end": {"x": line.end.x, "y": line.end.y},
    }


def autonomous_demo_report_payload(
    result: AutonomousDemoResult,
    configuration: AutonomousDemoConfiguration,
    *,
    video_path: Path,
    resources: RuntimeResourceSnapshot | None = None,
) -> dict[str, object]:
    """Build one path-free, deterministic report payload."""

    video_sha = _sha256(video_path)
    model_path = configuration.detector_configuration.model_path
    model_sha = _sha256(model_path) if model_path is not None else None
    seed = "|".join(
        (
            configuration.demo_id,
            video_sha or "unreadable_video",
            model_sha or "no_model",
            configuration.detector_configuration.fingerprint,
            configuration.execution_mode,
            str(result.primary_count),
        )
    )
    run_id = f"autonomous_{hashlib.sha256(seed.encode('utf-8')).hexdigest()[:16]}"
    return {
        "schema_version": "phase_10_3c_a3",
        "run_id": run_id,
        "video_id": configuration.demo_id,
        "video_sha256": video_sha,
        "model_identity": "hogflow_pig_demo_v2"
        if model_sha == "892a15ce4c739a819b17900700bd17c8473c44b6734b954869bf5470a633cc8c"
        else None,
        "model_sha256": model_sha,
        "detector_configuration_fingerprint": configuration.detector_configuration.fingerprint,
        "algorithm_version": result.calibration.algorithm_version,
        "execution_mode": configuration.execution_mode,
        "calibration": {
            "status": result.calibration.status.value,
            "confidence": result.calibration.confidence.value,
            "score": result.calibration.selected_score,
            "direction": result.primary_count_direction,
            "direction_purity": result.calibration.direction_purity,
            "line": _line_payload(result),
            "line_count_range": [
                result.calibration.line_count_min,
                result.calibration.line_count_max,
            ],
            "detector_count_range": [
                result.calibration.detector_count_min,
                result.calibration.detector_count_max,
            ],
            "corridor_coverage": result.calibration.corridor_coverage,
            "lost_near_line_ratio": result.calibration.lost_near_line_ratio,
            "crossing_local_continuity": result.calibration.crossing_local_continuity,
            "reason_codes": list(result.calibration.confidence_reason_codes),
        },
        "counting": {
            "primary_count": result.primary_count,
            "forward_crossings": result.forward_crossings,
            "reverse_crossings": result.reverse_crossings,
            "crossing_events": result.counting_crossing_events,
        },
        "tracking": {
            "tracks_observed": result.tracks_observed,
            "max_active_tracks": result.max_active_tracks,
            "id_switches": "NOT_MEASURED_WITHOUT_INDEPENDENT_GROUND_TRUTH",
            "fragmentation": "NOT_MEASURED_WITHOUT_INDEPENDENT_GROUND_TRUTH",
        },
        "performance": {
            "calibration_frames": result.calibration_frames,
            "counting_frames": result.counting_frames,
            "inference_passes": result.inference_passes,
            "cache_replay_used": result.cache_replay_used,
            "calibration_fps": result.calibration_fps,
            "counting_fps": result.counting_fps,
            "counting_fps_semantics": (
                "replay_decode_and_count_no_detector"
                if result.cache_replay_used
                else "detector_tracking_count"
            ),
            "average_detector_latency_ms": result.average_detector_latency_ms,
            "total_elapsed_seconds": result.total_elapsed_seconds,
            "peak_ram_mb": None if resources is None else resources.peak_ram_mb,
            "peak_vram_mb": None if resources is None else resources.peak_vram_mb,
            "resource_measurement": (
                "not_sampled_by_core_orchestration" if resources is None else resources.measurement
            ),
        },
        "warnings": [
            _NON_VERIFIED,
            "DEMO MODEL — NOT PRODUCTION VALIDATED",
            *result.limitations,
            *result.failures,
        ],
    }


def autonomous_demo_report_json(payload: dict[str, object]) -> str:
    return json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def autonomous_demo_report_markdown(payload: dict[str, object]) -> str:
    calibration = payload["calibration"]
    counting = payload["counting"]
    tracking = payload["tracking"]
    performance = payload["performance"]
    lines = [
        "# HogFlow Autonomous Counting Test",
        "",
        f"- Run: `{payload['run_id']}`",
        f"- Video ID: `{payload['video_id']}`",
        f"- Video SHA-256: `{payload['video_sha256'] or 'UNAVAILABLE'}`",
        f"- Model SHA-256: `{payload['model_sha256'] or 'UNAVAILABLE'}`",
        f"- Mode: `{payload['execution_mode']}`",
        f"- Algorithm: `{payload['algorithm_version']}`",
        "",
        f"- Calibration: `{calibration['status']}` / `{calibration['confidence']}`",
        f"- Direction: `{calibration['direction'] or 'UNKNOWN'}`",
        f"- Line: `{calibration['line'] or 'UNLOCKED'}`",
        f"- Technical count: `{counting['primary_count']}`",
        f"- Forward crossings: `{counting['forward_crossings']}`",
        f"- Reverse crossings: `{counting['reverse_crossings']}`",
        f"- Tracks observed: `{tracking['tracks_observed']}`",
        f"- Inference passes: `{performance['inference_passes']}`",
        f"- Replay cache used: `{str(performance['cache_replay_used']).lower()}`",
        f"- Counting FPS: `{performance['counting_fps']:.3f}`",
        f"- Counting FPS semantics: `{performance['counting_fps_semantics']}`",
        f"- Mean detector latency: `{performance['average_detector_latency_ms']:.3f} ms`",
        f"- Total elapsed: `{performance['total_elapsed_seconds']:.3f} s`",
        "",
        f"**{_NON_VERIFIED}**",
        "",
        "Warnings:",
    ]
    lines.extend(f"- {warning}" for warning in payload["warnings"])
    return "\n".join(lines) + "\n"


def write_autonomous_demo_report(
    result: AutonomousDemoResult,
    configuration: AutonomousDemoConfiguration,
    *,
    video_path: Path,
    output_root: Path,
    resources: RuntimeResourceSnapshot | None = None,
) -> AutonomousReportPaths:
    """Atomically write JSON and Markdown into an ignored local root."""

    if not isinstance(video_path, Path) or not isinstance(output_root, Path):
        raise TypeError("Autonomous reports require pathlib paths.")
    payload = autonomous_demo_report_payload(
        result,
        configuration,
        video_path=video_path,
        resources=resources,
    )
    root = output_root.resolve()
    root.mkdir(parents=True, exist_ok=True)
    run_id = str(payload["run_id"])
    json_path = root / f"{run_id}.json"
    markdown_path = root / f"{run_id}.md"
    _atomic_write(json_path, autonomous_demo_report_json(payload))
    _atomic_write(markdown_path, autonomous_demo_report_markdown(payload))
    return AutonomousReportPaths(json_path=json_path, markdown_path=markdown_path)


def _atomic_write(path: Path, content: str) -> None:
    with NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        newline="\n",
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
        delete=False,
    ) as stream:
        stream.write(content)
        temporary = Path(stream.name)
    try:
        os.replace(temporary, path)
    except OSError:
        temporary.unlink(missing_ok=True)
        raise


__all__ = [
    "AutonomousReportPaths",
    "RuntimeResourceSampler",
    "RuntimeResourceSnapshot",
    "autonomous_demo_report_json",
    "autonomous_demo_report_markdown",
    "autonomous_demo_report_payload",
    "write_autonomous_demo_report",
]
