from __future__ import annotations

from pathlib import Path
from time import sleep

from _phase9_helpers import LifecycleIdFactory, operator_application
from test_autonomous_demo_orchestration import (
    _configuration,
    _detector_factory,
    _source_factory,
    _tracker_factory,
)

from hogflow.application import OperatorApplicationService
from hogflow.calibration import AutonomousDemoConfiguration, run_autonomous_demo


def test_optimized_autonomous_run_replays_bounded_tracking_evidence() -> None:
    base = _configuration()
    configuration = AutonomousDemoConfiguration(
        demo_id=base.demo_id,
        detector_configuration=base.detector_configuration,
        tracker_configuration=base.tracker_configuration,
        calibration_settings=base.calibration_settings,
        execution_mode="optimized",
        replay_cache_max_frames=64,
    )

    result = run_autonomous_demo(
        configuration,
        source_factory=_source_factory,
        detector_factory=_detector_factory,
        tracker_factory=_tracker_factory,
    )

    assert result.primary_count == 3
    assert result.cache_replay_used is True
    assert result.inference_passes == 3
    assert result.tracks_observed == 3
    assert result.forward_crossings == 3
    assert result.reverse_crossings == 0


def test_replay_cache_overflow_falls_back_to_detector_count_pass() -> None:
    base = _configuration()
    configuration = AutonomousDemoConfiguration(
        demo_id=base.demo_id,
        detector_configuration=base.detector_configuration,
        tracker_configuration=base.tracker_configuration,
        calibration_settings=base.calibration_settings,
        execution_mode="optimized",
        replay_cache_max_frames=2,
    )

    result = run_autonomous_demo(
        configuration,
        source_factory=_source_factory,
        detector_factory=_detector_factory,
        tracker_factory=_tracker_factory,
    )

    assert result.primary_count == 3
    assert result.cache_replay_used is False
    assert result.inference_passes == 4


def test_legacy_mode_remains_available_for_before_after_benchmark() -> None:
    base = _configuration()
    configuration = AutonomousDemoConfiguration(
        demo_id=base.demo_id,
        detector_configuration=base.detector_configuration,
        tracker_configuration=base.tracker_configuration,
        calibration_settings=base.calibration_settings,
        execution_mode="legacy",
    )

    result = run_autonomous_demo(
        configuration,
        source_factory=_source_factory,
        detector_factory=_detector_factory,
        tracker_factory=_tracker_factory,
    )

    assert result.primary_count == 3
    assert result.cache_replay_used is False
    assert result.inference_passes == 4


def test_report_writer_is_path_free_and_explicitly_non_verified(tmp_path: Path) -> None:
    from hogflow.calibration.reporting import write_autonomous_demo_report

    base = _configuration()
    result = run_autonomous_demo(
        base,
        source_factory=_source_factory,
        detector_factory=_detector_factory,
        tracker_factory=_tracker_factory,
    )
    video = tmp_path / "private video.mp4"
    video.write_bytes(b"synthetic-video")
    paths = write_autonomous_demo_report(
        result,
        base,
        video_path=video,
        output_root=tmp_path / "reports",
    )

    payload = paths.json_path.read_text(encoding="utf-8")
    markdown = paths.markdown_path.read_text(encoding="utf-8")
    assert "AUTONOMOUS ESTIMATE — NOT INDEPENDENTLY VERIFIED" in payload
    assert "AUTONOMOUS ESTIMATE — NOT INDEPENDENTLY VERIFIED" in markdown
    assert str(video) not in payload
    assert str(video) not in markdown
    assert "synthetic-video" not in payload


def test_resource_sampler_is_bounded_and_sanitized() -> None:
    from hogflow.calibration.reporting import RuntimeResourceSampler

    sampler = RuntimeResourceSampler(sample_interval_seconds=0.01)
    sampler.start()
    sleep(0.03)
    snapshot = sampler.stop()

    assert snapshot.measurement in {
        "sampled_process_rss_and_device_vram",
        "sampled_process_rss_only",
        "unavailable",
    }
    assert snapshot.peak_ram_mb is None or snapshot.peak_ram_mb >= 0
    assert snapshot.peak_vram_mb is None or snapshot.peak_vram_mb >= 0


def test_local_report_action_is_bounded_and_does_not_expose_path(
    tmp_path: Path,
    monkeypatch,
) -> None:
    _application, coordinator = operator_application()
    report = tmp_path / "autonomous.md"
    report.write_text("technical report", encoding="utf-8")
    application = OperatorApplicationService(
        coordinator,
        crossing_lifecycle_id_factory=LifecycleIdFactory(),
        autonomous_report_path_supplier=lambda: report,
    )
    opened: list[str] = []
    monkeypatch.setattr(
        "hogflow.application.operator_service.os.startfile",
        lambda value: opened.append(value),
        raising=False,
    )

    assert application.autonomous_report_available() is True
    application.view_autonomous_report()
    assert opened == [str(report)]
