"""Ultralytics YOLO implementation of the detector-training contract."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
from collections.abc import Mapping
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path, PurePosixPath
from typing import Any, Callable

from hogflow.core import (
    ConfigurationError,
    DependencyUnavailableError,
    HogFlowError,
    InputDataError,
    get_logger,
)
from hogflow.models import BoundingBox
from hogflow.training.configuration import TrainingConfiguration
from hogflow.training.dataset import (
    build_detection_frame,
    frame_record,
    image_path_for_frame,
)
from hogflow.training.models import (
    DetectorTrainingOutput,
    DetectorValidationOutput,
    FrameworkMetric,
    PreparedTrainingDataset,
    ValidationPrediction,
)

LOGGER = get_logger(__name__)
_YoloFactory = Callable[[str], Any]


class YOLOBaselineTrainer:
    """Train one local Ultralytics YOLO baseline behind HogFlow contracts.

    Ultralytics is imported lazily when this adapter is constructed. Training,
    validation, result tensors, and framework metrics remain private. The
    adapter returns only immutable HogFlow values and local checkpoint paths.
    """

    def __init__(
        self,
        model_reference: str,
        output_root: str | Path,
        *,
        yolo_factory: _YoloFactory | None = None,
        framework_version: str | None = None,
    ) -> None:
        if not isinstance(model_reference, str) or not model_reference.strip():
            raise ConfigurationError("YOLO model reference must be non-empty text.")
        self._model_source = model_reference.strip()
        self._output_root = Path(output_root)
        self._prepare_output_directories()
        if yolo_factory is None:
            self._configure_local_framework_caches()
            self._yolo_factory, detected_version = _load_yolo_runtime()
            self._framework_version = detected_version
        else:
            self._yolo_factory = yolo_factory
            self._framework_version = framework_version or "test-backend"

    @property
    def trainer_name(self) -> str:
        """Return the concrete adapter identity."""

        return "ultralytics-yolo"

    @property
    def trainer_version(self) -> str:
        """Return the installed Ultralytics version."""

        return self._framework_version

    @property
    def model_reference(self) -> str:
        """Return only the model filename for sanitized provenance."""

        return PurePosixPath(self._model_source.replace("\\", "/")).name

    def train(
        self,
        dataset: PreparedTrainingDataset,
        configuration: TrainingConfiguration,
        *,
        resume_checkpoint: Path | None = None,
    ) -> DetectorTrainingOutput:
        """Train one bounded baseline and copy its best checkpoint locally."""

        _validate_inputs(dataset, configuration)
        resume = _validate_resume_checkpoint(resume_checkpoint)
        dataset_yaml = self._write_dataset_yaml(dataset, configuration.run_name)
        model_source = str(resume) if resume is not None else self._model_source
        try:
            model = self._yolo_factory(model_source)
            arguments: dict[str, object] = {
                "batch": configuration.batch_size,
                "cache": False,
                "data": str(dataset_yaml),
                "deterministic": configuration.deterministic,
                "device": configuration.device,
                "epochs": configuration.epochs,
                "exist_ok": True,
                "imgsz": configuration.image_size,
                "name": configuration.run_name,
                "optimizer": configuration.optimizer,
                "plots": False,
                "project": str(self._output_root / "runs" / "training"),
                "save": True,
                "seed": configuration.seed,
                "verbose": False,
                "workers": configuration.workers,
            }
            if resume is not None:
                arguments["resume"] = str(resume)
            framework_result = model.train(**arguments)
            checkpoint = _trainer_checkpoint(model)
        except HogFlowError:
            raise
        except Exception as exc:
            raise HogFlowError(
                "YOLO baseline training failed for the local prepared dataset."
            ) from exc

        exported_checkpoint = self._output_root / "models" / configuration.run_name / "best.pt"
        _copy_checkpoint(
            checkpoint,
            exported_checkpoint,
            allow_replace=resume is not None,
        )
        return DetectorTrainingOutput(
            run_id=configuration.run_name,
            best_checkpoint_path=exported_checkpoint,
            framework_metrics=_framework_metrics(framework_result),
        )

    def validate(
        self,
        dataset: PreparedTrainingDataset,
        checkpoint_path: Path,
        configuration: TrainingConfiguration,
    ) -> DetectorValidationOutput:
        """Validate and convert YOLO predictions to Phase 4.1 evaluation frames."""

        _validate_inputs(dataset, configuration)
        if not isinstance(checkpoint_path, Path) or not checkpoint_path.is_file():
            raise InputDataError("The local detector checkpoint is missing or is not a file.")
        frame_ids = dataset.frame_ids_for(configuration.evaluation_split)
        if not frame_ids:
            raise InputDataError("The selected evaluation split contains no finalized frames.")
        dataset_yaml = self._write_dataset_yaml(dataset, configuration.run_name)
        try:
            model = self._yolo_factory(str(checkpoint_path))
            framework_result = model.val(
                batch=configuration.batch_size,
                data=str(dataset_yaml),
                deterministic=configuration.deterministic,
                device=configuration.device,
                exist_ok=True,
                imgsz=configuration.image_size,
                name=f"{configuration.run_name}-validation",
                plots=False,
                project=str(self._output_root / "runs" / "validation"),
                save_json=False,
                seed=configuration.seed,
                split=_framework_split(configuration.evaluation_split),
                verbose=False,
                workers=configuration.workers,
            )
            image_paths = [str(image_path_for_frame(dataset, frame_id)) for frame_id in frame_ids]
            prediction_results = model.predict(
                source=image_paths,
                classes=[0],
                conf=configuration.confidence_threshold,
                device=configuration.device,
                imgsz=configuration.image_size,
                save=False,
                verbose=False,
            )
        except Exception as exc:
            raise HogFlowError(
                "YOLO baseline validation failed for the opaque evaluation split."
            ) from exc
        if len(prediction_results) != len(frame_ids):
            raise HogFlowError("YOLO returned an unexpected number of validation results.")

        frames = tuple(
            sorted(
                (
                    _validation_frame(dataset, frame_id, result)
                    for frame_id, result in zip(frame_ids, prediction_results, strict=True)
                ),
                key=lambda frame: (frame.source_video_id, frame.frame_id),
            )
        )
        return DetectorValidationOutput(
            frames=frames,
            framework_metrics=_framework_metrics(framework_result),
        )

    def _prepare_output_directories(self) -> None:
        for name in ("evaluation", "metrics", "models", "runs", "tensorboard"):
            (self._output_root / name).mkdir(parents=True, exist_ok=True)

    def _configure_local_framework_caches(self) -> None:
        cache_root = (self._output_root / "runs" / ".framework-cache").resolve()
        matplotlib_root = cache_root / "matplotlib"
        yolo_root = cache_root / "yolo"
        matplotlib_root.mkdir(parents=True, exist_ok=True)
        (yolo_root / "Ultralytics").mkdir(parents=True, exist_ok=True)
        os.environ["MPLCONFIGDIR"] = str(matplotlib_root)
        os.environ["YOLO_CONFIG_DIR"] = str(yolo_root)

    def _write_dataset_yaml(
        self,
        dataset: PreparedTrainingDataset,
        run_name: str,
    ) -> Path:
        target = self._output_root / "metrics" / run_name / "dataset.local.yaml"
        lines = [
            f"path: {json.dumps(str(dataset.root.resolve()))}",
            "train: images/train",
            "val: images/validation",
        ]
        if dataset.test_frame_ids:
            lines.append("test: images/test")
        lines.extend(("names:", "  0: pig", ""))
        _atomic_write_text(target, "\n".join(lines))
        return target


def _load_yolo_runtime() -> tuple[_YoloFactory, str]:
    try:
        from ultralytics import YOLO
    except ImportError as exc:
        raise DependencyUnavailableError(
            "Ultralytics is required for the YOLO baseline trainer."
        ) from exc
    try:
        framework_version = version("ultralytics")
    except PackageNotFoundError:
        framework_version = "unknown"
    return YOLO, framework_version


def _validate_inputs(
    dataset: PreparedTrainingDataset,
    configuration: TrainingConfiguration,
) -> None:
    if not isinstance(dataset, PreparedTrainingDataset):
        raise InputDataError("dataset must be PreparedTrainingDataset.")
    if not isinstance(configuration, TrainingConfiguration):
        raise InputDataError("configuration must be TrainingConfiguration.")


def _validate_resume_checkpoint(checkpoint: Path | None) -> Path | None:
    if checkpoint is None:
        return None
    if not isinstance(checkpoint, Path) or not checkpoint.is_file():
        raise InputDataError("Resume checkpoint is missing or is not a local file.")
    return checkpoint


def _trainer_checkpoint(model: Any) -> Path:
    trainer = getattr(model, "trainer", None)
    best = Path(getattr(trainer, "best", ""))
    last = Path(getattr(trainer, "last", ""))
    checkpoint = best if best.is_file() else last
    if not checkpoint.is_file():
        raise HogFlowError("YOLO training completed without a readable checkpoint.")
    return checkpoint


def _copy_checkpoint(source: Path, destination: Path, *, allow_replace: bool) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.is_file() and not allow_replace:
        if _sha256(source) == _sha256(destination):
            return
        raise InputDataError(
            "A different local checkpoint already exists for this run name; choose a new run name."
        )
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            dir=destination.parent,
            prefix=f".{destination.name}.",
            suffix=".tmp",
            delete=False,
        ) as output:
            temporary = Path(output.name)
            with source.open("rb") as input_file:
                shutil.copyfileobj(input_file, output)
            output.flush()
            os.fsync(output.fileno())
        temporary.replace(destination)
    except OSError as exc:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
        raise InputDataError("Unable to export the best local detector checkpoint.") from exc


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as input_file:
        for chunk in iter(lambda: input_file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _framework_metrics(result: Any) -> tuple[FrameworkMetric, ...]:
    if result is None:
        return ()
    values: Mapping[Any, Any]
    if isinstance(result, Mapping):
        values = result
    else:
        values = getattr(result, "results_dict", {})
    metrics: list[FrameworkMetric] = []
    for name, value in values.items():
        try:
            metrics.append(FrameworkMetric(str(name), float(value)))
        except (TypeError, ValueError, InputDataError):
            continue
    return tuple(sorted(metrics, key=lambda metric: metric.name))


def _framework_split(split: Any) -> str:
    if getattr(split, "value", None) == "validation":
        return "val"
    if getattr(split, "value", None) == "test":
        return "test"
    raise InputDataError("YOLO evaluation supports only validation or test splits.")


def _validation_frame(
    dataset: PreparedTrainingDataset,
    frame_id: str,
    result: Any,
):
    record = frame_record(dataset, frame_id)
    return build_detection_frame(
        dataset,
        frame_id,
        _predictions(result, width=record.width, height=record.height),
    )


def _predictions(
    result: Any,
    *,
    width: int,
    height: int,
) -> tuple[ValidationPrediction, ...]:
    boxes = getattr(result, "boxes", None)
    if boxes is None or len(boxes) == 0:
        return ()
    coordinates = _to_rows(boxes.xyxy)
    confidence_values = _to_rows(boxes.conf)
    class_values = _to_rows(boxes.cls)
    predictions: list[ValidationPrediction] = []
    for row, confidence, class_id in zip(coordinates, confidence_values, class_values, strict=True):
        if int(class_id) != 0:
            continue
        x_min, y_min, x_max, y_max = (float(value) for value in row)
        x_min = min(max(x_min, 0.0), float(width))
        y_min = min(max(y_min, 0.0), float(height))
        x_max = min(max(x_max, 0.0), float(width))
        y_max = min(max(y_max, 0.0), float(height))
        if x_min >= x_max or y_min >= y_max:
            continue
        predictions.append(
            ValidationPrediction(
                bounding_box=BoundingBox(x_min, y_min, x_max, y_max),
                confidence=float(confidence),
            )
        )
    return tuple(predictions)


def _to_rows(value: Any) -> list[Any]:
    if hasattr(value, "cpu"):
        value = value.cpu()
    if hasattr(value, "tolist"):
        return value.tolist()
    return list(value)


def _atomic_write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as output:
            temporary = Path(output.name)
            output.write(content)
            output.flush()
            os.fsync(output.fileno())
        temporary.replace(path)
    except OSError as exc:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
        raise InputDataError("Unable to write the local detector dataset configuration.") from exc


__all__ = ["YOLOBaselineTrainer"]
