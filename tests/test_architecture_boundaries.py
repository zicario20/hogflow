import ast
import subprocess
import sys
from pathlib import Path

SOURCE_ROOT = Path(__file__).resolve().parents[1] / "src" / "hogflow"
INTERNAL_PACKAGES = {
    "adapters",
    "annotation",
    "config",
    "core",
    "counting",
    "data",
    "detection",
    "domain",
    "evaluation",
    "models",
    "pipeline",
    "sessions",
    "storage",
    "streaming",
    "training",
    "tracking",
    "video",
}
FORBIDDEN_IMPORTS = {
    "adapters": {
        "annotation",
        "counting",
        "data",
        "domain",
        "evaluation",
        "pipeline",
        "sessions",
        "storage",
    },
    "core": {
        "annotation",
        "adapters",
        "config",
        "counting",
        "data",
        "video",
        "detection",
        "tracking",
        "models",
        "pipeline",
        "sessions",
        "storage",
        "domain",
        "evaluation",
        "training",
        "streaming",
    },
    "config": {
        "annotation",
        "adapters",
        "counting",
        "data",
        "video",
        "detection",
        "tracking",
        "models",
        "pipeline",
        "sessions",
        "storage",
        "domain",
        "evaluation",
        "training",
        "streaming",
    },
    "counting": {
        "annotation",
        "adapters",
        "data",
        "video",
        "detection",
        "tracking",
        "models",
        "pipeline",
        "sessions",
        "storage",
        "evaluation",
        "training",
        "streaming",
    },
    "domain": {
        "annotation",
        "adapters",
        "config",
        "counting",
        "data",
        "video",
        "detection",
        "tracking",
        "models",
        "pipeline",
        "sessions",
        "storage",
        "evaluation",
        "training",
        "streaming",
    },
    "models": {
        "annotation",
        "adapters",
        "config",
        "counting",
        "data",
        "video",
        "detection",
        "tracking",
        "pipeline",
        "sessions",
        "storage",
        "domain",
        "evaluation",
        "training",
        "streaming",
    },
    "detection": {
        "adapters",
        "annotation",
        "config",
        "counting",
        "data",
        "domain",
        "evaluation",
        "pipeline",
        "sessions",
        "storage",
        "tracking",
        "training",
        "video",
    },
    "pipeline": {"adapters", "annotation", "data", "evaluation", "training"},
    "data": {
        "adapters",
        "counting",
        "detection",
        "domain",
        "models",
        "pipeline",
        "sessions",
        "storage",
        "tracking",
        "evaluation",
        "training",
        "streaming",
    },
    "evaluation": {
        "adapters",
        "annotation",
        "config",
        "counting",
        "data",
        "detection",
        "domain",
        "pipeline",
        "sessions",
        "storage",
        "tracking",
        "video",
        "training",
        "streaming",
    },
    "annotation": {
        "adapters",
        "config",
        "counting",
        "data",
        "detection",
        "domain",
        "pipeline",
        "sessions",
        "storage",
        "tracking",
        "video",
        "training",
        "streaming",
    },
    "training": {
        "adapters",
        "config",
        "counting",
        "data",
        "detection",
        "domain",
        "pipeline",
        "sessions",
        "storage",
        "tracking",
        "video",
        "streaming",
    },
    "streaming": {
        "adapters",
        "annotation",
        "config",
        "counting",
        "data",
        "detection",
        "domain",
        "evaluation",
        "models",
        "pipeline",
        "sessions",
        "storage",
        "tracking",
        "training",
        "video",
    },
    "tracking": {
        "adapters",
        "annotation",
        "config",
        "counting",
        "data",
        "domain",
        "evaluation",
        "pipeline",
        "sessions",
        "storage",
        "training",
        "video",
    },
}
CONTRACT_LAYER_FILES = (
    SOURCE_ROOT / "models.py",
    SOURCE_ROOT / "detection" / "contracts.py",
    SOURCE_ROOT / "tracking" / "contracts.py",
    SOURCE_ROOT / "video" / "contracts.py",
)
PROTOCOL_CONTRACT_FILES = CONTRACT_LAYER_FILES[1:]
FORBIDDEN_CONTRACT_IMPORTS = {
    "botsort",
    "bytetrack",
    "cv2",
    "numpy",
    "onnxruntime",
    "opencv",
    "supervision",
    "tensorrt",
    "torch",
    "ultralytics",
}
FRAMEWORK_INDEPENDENT_FILES = (
    SOURCE_ROOT / "models.py",
    SOURCE_ROOT / "counting" / "line_crossing.py",
    SOURCE_ROOT / "detection" / "contracts.py",
    SOURCE_ROOT / "tracking" / "contracts.py",
    SOURCE_ROOT / "video" / "contracts.py",
    SOURCE_ROOT / "pipeline" / "models.py",
    SOURCE_ROOT / "pipeline" / "generic_counting_pipeline.py",
    SOURCE_ROOT / "data" / "models.py",
    SOURCE_ROOT / "data" / "validation.py",
    SOURCE_ROOT / "evaluation" / "detection_models.py",
    SOURCE_ROOT / "evaluation" / "detection_metrics.py",
    SOURCE_ROOT / "evaluation" / "dataset_selection.py",
    SOURCE_ROOT / "annotation" / "models.py",
    SOURCE_ROOT / "annotation" / "policy.py",
    SOURCE_ROOT / "annotation" / "yolo.py",
    SOURCE_ROOT / "annotation" / "manifest.py",
    SOURCE_ROOT / "data" / "dataset_splitting.py",
    SOURCE_ROOT / "data" / "frame_selection.py",
    SOURCE_ROOT / "training" / "configuration.py",
    SOURCE_ROOT / "training" / "contracts.py",
    SOURCE_ROOT / "training" / "models.py",
    SOURCE_ROOT / "training" / "dataset.py",
    SOURCE_ROOT / "training" / "failure_analysis.py",
    SOURCE_ROOT / "training" / "reporting.py",
    SOURCE_ROOT / "training" / "baseline.py",
    SOURCE_ROOT / "streaming" / "models.py",
    SOURCE_ROOT / "streaming" / "configuration.py",
    SOURCE_ROOT / "streaming" / "contracts.py",
    SOURCE_ROOT / "streaming" / "buffering.py",
    SOURCE_ROOT / "streaming" / "health.py",
    SOURCE_ROOT / "streaming" / "lifecycle.py",
    SOURCE_ROOT / "streaming" / "errors.py",
    SOURCE_ROOT / "streaming" / "sanitization.py",
    SOURCE_ROOT / "streaming" / "synthetic.py",
    SOURCE_ROOT / "detection" / "errors.py",
    SOURCE_ROOT / "detection" / "inference.py",
    SOURCE_ROOT / "detection" / "ports.py",
    SOURCE_ROOT / "detection" / "telemetry.py",
    SOURCE_ROOT / "detection" / "fakes.py",
    SOURCE_ROOT / "pipeline" / "live_detection_pipeline.py",
    SOURCE_ROOT / "tracking" / "config.py",
    SOURCE_ROOT / "tracking" / "errors.py",
    SOURCE_ROOT / "tracking" / "fakes.py",
    SOURCE_ROOT / "tracking" / "models.py",
    SOURCE_ROOT / "tracking" / "ports.py",
    SOURCE_ROOT / "tracking" / "telemetry.py",
    SOURCE_ROOT / "pipeline" / "live_tracking_pipeline.py",
)


def _module_parts(path: Path) -> tuple[str, ...]:
    relative_parts = path.relative_to(SOURCE_ROOT).with_suffix("").parts
    module_parts = ("hogflow", *relative_parts)
    if module_parts[-1] == "__init__":
        return module_parts[:-1]
    return module_parts


def _target_package(module_parts: tuple[str, ...]) -> str | None:
    if (
        len(module_parts) >= 2
        and module_parts[0] == "hogflow"
        and module_parts[1] in INTERNAL_PACKAGES
    ):
        return module_parts[1]
    return None


def _resolved_from_module(
    node: ast.ImportFrom,
    source_module: tuple[str, ...],
    *,
    source_is_package: bool,
) -> tuple[str, ...]:
    if node.level == 0:
        return tuple(node.module.split(".")) if node.module else ()

    source_package = source_module if source_is_package else source_module[:-1]
    parent_steps = node.level - 1
    if parent_steps > len(source_package):
        return ()
    base = source_package[: len(source_package) - parent_steps]
    if node.module:
        return (*base, *node.module.split("."))
    return base


def _internal_imports(
    tree: ast.AST,
    source_module: tuple[str, ...],
    *,
    source_is_package: bool,
) -> list[tuple[int, str]]:
    imports: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                target = _target_package(tuple(alias.name.split(".")))
                if target is not None:
                    imports.append((node.lineno, target))
        elif isinstance(node, ast.ImportFrom):
            resolved_module = _resolved_from_module(
                node,
                source_module,
                source_is_package=source_is_package,
            )
            target = _target_package(resolved_module)
            if target is not None:
                imports.append((node.lineno, target))
            elif resolved_module == ("hogflow",):
                for alias in node.names:
                    if alias.name in INTERNAL_PACKAGES:
                        imports.append((node.lineno, alias.name))
    return imports


def test_internal_package_dependencies_follow_declared_boundaries() -> None:
    violations: list[str] = []
    for source_file in sorted(SOURCE_ROOT.rglob("*.py")):
        if "__pycache__" in source_file.parts or source_file.name.endswith("_generated.py"):
            continue

        source_module = _module_parts(source_file)
        source_package = source_module[1] if len(source_module) >= 2 else None
        forbidden_targets = FORBIDDEN_IMPORTS.get(source_package, set())
        tree = ast.parse(source_file.read_text(encoding="utf-8"), filename=str(source_file))
        for line_number, target_package in _internal_imports(
            tree,
            source_module,
            source_is_package=source_file.name == "__init__.py",
        ):
            if target_package in forbidden_targets:
                relative_file = source_file.relative_to(SOURCE_ROOT.parent)
                violations.append(
                    f"{relative_file}:{line_number}: package {source_package!r} "
                    f"must not import {target_package!r}"
                )

    assert not violations, "Architecture dependency violations:\n" + "\n".join(violations)


def test_internal_import_parser_handles_supported_import_forms() -> None:
    tree = ast.parse(
        "\n".join(
            (
                "import hogflow.video",
                "from hogflow.video import generic_counter",
                "from hogflow import video",
                "from ..tracking import adapter",
                "import logging",
            )
        )
    )

    imports = _internal_imports(
        tree,
        ("hogflow", "core", "sample"),
        source_is_package=False,
    )

    assert {target for _line, target in imports} == {"tracking", "video"}


def test_contract_layer_has_no_computer_vision_framework_imports() -> None:
    violations: list[str] = []
    for source_file in CONTRACT_LAYER_FILES:
        tree = ast.parse(source_file.read_text(encoding="utf-8"), filename=str(source_file))
        for node in ast.walk(tree):
            imported_roots: list[str] = []
            if isinstance(node, ast.Import):
                imported_roots.extend(alias.name.split(".", maxsplit=1)[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported_roots.append(node.module.split(".", maxsplit=1)[0])

            for imported_root in imported_roots:
                if imported_root in FORBIDDEN_CONTRACT_IMPORTS:
                    relative_file = source_file.relative_to(SOURCE_ROOT.parent)
                    violations.append(f"{relative_file}:{node.lineno}: imports {imported_root!r}")

    assert not violations, "Framework imports in contract layer:\n" + "\n".join(violations)


def test_core_counting_contracts_and_pipeline_have_no_framework_imports() -> None:
    violations: list[str] = []
    for source_file in FRAMEWORK_INDEPENDENT_FILES:
        tree = ast.parse(source_file.read_text(encoding="utf-8"), filename=str(source_file))
        for node in ast.walk(tree):
            imported_roots: list[str] = []
            if isinstance(node, ast.Import):
                imported_roots.extend(alias.name.split(".", maxsplit=1)[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported_roots.append(node.module.split(".", maxsplit=1)[0])
            for imported_root in imported_roots:
                if imported_root in FORBIDDEN_CONTRACT_IMPORTS:
                    relative_file = source_file.relative_to(SOURCE_ROOT.parent)
                    violations.append(f"{relative_file}:{node.lineno}: imports {imported_root!r}")

    assert not violations, "Framework imports in independent layers:\n" + "\n".join(violations)


def test_protocol_contracts_depend_only_on_shared_models() -> None:
    violations: list[str] = []
    for source_file in PROTOCOL_CONTRACT_FILES:
        source_module = _module_parts(source_file)
        tree = ast.parse(source_file.read_text(encoding="utf-8"), filename=str(source_file))
        imported_packages = {
            target
            for _line, target in _internal_imports(
                tree,
                source_module,
                source_is_package=False,
            )
        }
        if imported_packages != {"models"}:
            relative_file = source_file.relative_to(SOURCE_ROOT.parent)
            violations.append(f"{relative_file}: imports {sorted(imported_packages)!r}")

    assert not violations, "Protocol dependency violations:\n" + "\n".join(violations)


def test_foundation_package_imports_do_not_write_to_stdout_or_stderr() -> None:
    package_names = (
        "hogflow.core",
        "hogflow.config",
        "hogflow.counting",
        "hogflow.models",
        "hogflow.data",
        "hogflow.data.models",
        "hogflow.data.validation",
        "hogflow.data.dataset_splitting",
        "hogflow.data.frame_selection",
        "hogflow.data.frame_extraction",
        "hogflow.annotation",
        "hogflow.annotation.models",
        "hogflow.annotation.policy",
        "hogflow.annotation.yolo",
        "hogflow.annotation.manifest",
        "hogflow.annotation.validation",
        "hogflow.evaluation",
        "hogflow.evaluation.detection_models",
        "hogflow.evaluation.detection_metrics",
        "hogflow.evaluation.dataset_selection",
        "hogflow.training",
        "hogflow.training.configuration",
        "hogflow.training.contracts",
        "hogflow.training.models",
        "hogflow.training.dataset",
        "hogflow.training.failure_analysis",
        "hogflow.training.reporting",
        "hogflow.training.baseline",
        "hogflow.streaming",
        "hogflow.streaming.models",
        "hogflow.streaming.configuration",
        "hogflow.streaming.contracts",
        "hogflow.streaming.buffering",
        "hogflow.streaming.health",
        "hogflow.streaming.lifecycle",
        "hogflow.streaming.errors",
        "hogflow.streaming.sanitization",
        "hogflow.streaming.synthetic",
        "hogflow.detection",
        "hogflow.detection.contracts",
        "hogflow.detection.errors",
        "hogflow.detection.inference",
        "hogflow.detection.ports",
        "hogflow.detection.telemetry",
        "hogflow.detection.fakes",
        "hogflow.tracking",
        "hogflow.tracking.contracts",
        "hogflow.tracking.config",
        "hogflow.tracking.errors",
        "hogflow.tracking.fakes",
        "hogflow.tracking.models",
        "hogflow.tracking.ports",
        "hogflow.tracking.telemetry",
        "hogflow.video",
        "hogflow.video.contracts",
        "hogflow.video.metadata",
        "hogflow.adapters",
        "hogflow.adapters.yolo_baseline_trainer",
        "hogflow.adapters.yolo_training",
        "hogflow.adapters.opencv_camera_source",
        "hogflow.adapters.opencv_file_stream_source",
        "hogflow.adapters.camera_source_factory",
        "hogflow.adapters.camera_stream_cli",
        "hogflow.adapters.ultralytics_live_detector",
        "hogflow.adapters.opencv_detection_preview",
        "hogflow.adapters.opencv_tracking_preview",
        "hogflow.adapters.supervision_bytetrack",
        "hogflow.pipeline",
        "hogflow.pipeline.models",
        "hogflow.pipeline.generic_counting_pipeline",
        "hogflow.pipeline.live_detection_pipeline",
        "hogflow.pipeline.live_tracking_pipeline",
        "hogflow.video.live_detection_cli",
        "hogflow.sessions",
        "hogflow.storage",
        "hogflow.domain",
    )

    for package_name in package_names:
        result = subprocess.run(
            [
                sys.executable,
                "-c",
                (
                    "import importlib, sys; "
                    "sys.path.insert(0, sys.argv[1]); "
                    "importlib.import_module(sys.argv[2])"
                ),
                str(SOURCE_ROOT.parent),
                package_name,
            ],
            check=False,
            capture_output=True,
            text=True,
        )

        assert result.returncode == 0, f"{package_name} failed to import: {result.stderr}"
        assert result.stdout == "", f"{package_name} wrote to stdout during import"
        assert result.stderr == "", f"{package_name} wrote to stderr during import"


def test_phase_5_3_tracking_core_has_no_counting_or_framework_implementation() -> None:
    files = (
        SOURCE_ROOT / "tracking" / "config.py",
        SOURCE_ROOT / "tracking" / "errors.py",
        SOURCE_ROOT / "tracking" / "fakes.py",
        SOURCE_ROOT / "tracking" / "models.py",
        SOURCE_ROOT / "tracking" / "ports.py",
        SOURCE_ROOT / "tracking" / "telemetry.py",
        SOURCE_ROOT / "pipeline" / "live_tracking_pipeline.py",
    )
    forbidden_tokens = (
        "DirectionalLineCounter",
        "line_crossing",
        "counted_tracker_ids",
        "cv2",
        "supervision",
        "ultralytics",
    )

    violations = [
        f"{source_file.name}: {token}"
        for source_file in files
        for token in forbidden_tokens
        if token in source_file.read_text(encoding="utf-8")
    ]

    assert not violations
