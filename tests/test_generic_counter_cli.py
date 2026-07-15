import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from hogflow.counting import CrossingDirection, CrossingEvent, Point
from hogflow.models import Frame
from hogflow.video import generic_counter


def _required_arguments(tmp_path: Path) -> list[str]:
    input_path = tmp_path / "input.avi"
    input_path.touch()
    return [
        "--input",
        str(input_path),
        "--output",
        str(tmp_path / "output.avi"),
        "--events",
        str(tmp_path / "events.jsonl"),
        "--class",
        "person",
        "--line-start",
        "0,10",
        "--line-end",
        "10,10",
        "--positive-direction",
        "negative-to-positive",
    ]


def test_parser_preserves_all_phase_1_arguments(tmp_path: Path) -> None:
    arguments = _required_arguments(tmp_path) + [
        "--confidence",
        "0.5",
        "--line-epsilon",
        "2",
        "--model",
        "generic.pt",
        "--device",
        "cpu",
        "--show",
        "--max-frames",
        "25",
    ]

    parsed = generic_counter.build_parser().parse_args(arguments)

    assert parsed.class_name == "person"
    assert parsed.confidence == 0.5
    assert parsed.line_epsilon == 2.0
    assert parsed.model == "generic.pt"
    assert parsed.device == "cpu"
    assert parsed.show is True
    assert parsed.max_frames == 25


def test_required_arguments_remain_required() -> None:
    with pytest.raises(SystemExit) as exc_info:
        generic_counter.build_parser().parse_args([])

    assert exc_info.value.code == 2


def test_invalid_line_is_rejected_by_parser(tmp_path: Path) -> None:
    arguments = _required_arguments(tmp_path)
    arguments[arguments.index("0,10")] = "not-a-point"

    with pytest.raises(SystemExit) as exc_info:
        generic_counter.build_parser().parse_args(arguments)

    assert exc_info.value.code == 2


def test_invalid_confidence_is_rejected_by_cli(tmp_path: Path) -> None:
    with pytest.raises(SystemExit) as exc_info:
        generic_counter.main(_required_arguments(tmp_path) + ["--confidence", "0"])

    assert exc_info.value.code == 2


def test_invalid_direction_is_rejected_by_parser(tmp_path: Path) -> None:
    arguments = _required_arguments(tmp_path)
    arguments[-1] = "sideways"

    with pytest.raises(SystemExit) as exc_info:
        generic_counter.build_parser().parse_args(arguments)

    assert exc_info.value.code == 2


def test_run_generic_counter_composes_adapters_pipeline_and_event_log(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    input_path = tmp_path / "input.avi"
    input_path.touch()
    calls: dict[str, object] = {}

    class FakeSource:
        fps = 10.0
        width = 20
        height = 20

        def __init__(self, path: Path) -> None:
            calls["source_path"] = path
            self.closed = False

        def close(self) -> None:
            self.closed = True
            calls["source_closed"] = True

    class FakeDetector:
        def __init__(self, *arguments: object) -> None:
            calls["detector_arguments"] = arguments

    class FakeTracker:
        def __init__(self, configuration: str) -> None:
            calls["tracker_configuration"] = configuration

    class FakeOutput:
        def __init__(self, path: Path, **arguments: object) -> None:
            calls["output_path"] = path
            calls["output_arguments"] = arguments

        def __call__(self, _result: object) -> bool:
            return True

        def close(self) -> None:
            calls["output_closed"] = True

    class FakePipeline:
        def __init__(self, *arguments: object, **keywords: object) -> None:
            calls["pipeline_arguments"] = arguments
            calls["pipeline_keywords"] = keywords

        def run(self, **arguments: object) -> SimpleNamespace:
            calls["run_arguments"] = arguments
            event = CrossingEvent(
                tracker_id=3,
                direction=CrossingDirection.NEGATIVE_TO_POSITIVE,
                counted=True,
                previous_point=Point(5, 7),
                current_point=Point(5, 13),
            )
            frame = Frame(1, 20, 20, bytes(1200), 0.1)
            arguments["on_event"](event, frame, 1)  # type: ignore[operator]
            return SimpleNamespace(processed_frames=2, positive_count=1)

    monkeypatch.setattr(generic_counter, "OpenCVVideoSource", FakeSource)
    monkeypatch.setattr(generic_counter, "UltralyticsDetector", FakeDetector)
    monkeypatch.setattr(generic_counter, "UltralyticsTracker", FakeTracker)
    monkeypatch.setattr(generic_counter, "OpenCVAnnotatedVideoOutput", FakeOutput)
    monkeypatch.setattr(generic_counter, "GenericCountingPipeline", FakePipeline)
    config = generic_counter.GenericCounterConfig(
        input_path=input_path,
        output_path=tmp_path / "output.avi",
        events_path=tmp_path / "events.jsonl",
        class_name="person",
        line=generic_counter.Line(Point(0, 10), Point(10, 10)),
        positive_direction=CrossingDirection.NEGATIVE_TO_POSITIVE,
    )

    count = generic_counter.run_generic_counter(config)

    assert count == 1
    assert calls["tracker_configuration"] == "bytetrack.yaml"
    assert calls["source_closed"] is True
    assert calls["output_closed"] is True
    payload = json.loads(config.events_path.read_text(encoding="utf-8"))
    assert set(payload) == {
        "counted",
        "current_point",
        "current_positive_count",
        "direction",
        "frame_index",
        "previous_point",
        "timestamp_seconds",
        "tracker_id",
    }
