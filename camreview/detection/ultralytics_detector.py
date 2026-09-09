from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import numpy as np

from ..errors import DetectorUnavailableError
from ..models import ObjectDetection
from .base import ObjectDetector
from .categories import category_for


class UltralyticsDetector(ObjectDetector):
    def __init__(self, model: str, device: str, confidence: float) -> None:
        self.model_path = model
        self.requested_device = device
        self.confidence = confidence
        self.model: Any = None
        self.device = "cpu"
        self.device_name = "CPU"
        self.name = f"Ultralytics YOLO ({model})"

    @staticmethod
    def _cache_directory() -> Path:
        if os.name == "nt":
            root = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
            return root / "CamReview" / "models"
        root = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache"))
        return root / "camreview" / "models"

    def _resolved_model(self) -> Path:
        configured = Path(self.model_path).expanduser()
        if configured.is_file() or configured.is_absolute() or configured.parent != Path("."):
            return configured
        return self._cache_directory() / configured.name

    def load(self) -> None:
        try:
            import torch
            from ultralytics import YOLO
        except ImportError as exc:
            raise DetectorUnavailableError(
                "Classification requires the optional dependencies; install with "
                'pip install -e ".[detect]"'
            ) from exc
        cuda_available = bool(torch.cuda.is_available())
        if self.requested_device.startswith("cuda") and not cuda_available:
            raise DetectorUnavailableError(
                f"CUDA was explicitly requested ({self.requested_device}) but is unavailable"
            )
        if self.requested_device == "auto":
            self.device = "cuda:0" if cuda_available else "cpu"
        else:
            self.device = self.requested_device
        if self.device.startswith("cuda"):
            index = int(self.device.split(":", maxsplit=1)[1]) if ":" in self.device else 0
            self.device_name = str(torch.cuda.get_device_name(index))
        else:
            self.device_name = "CPU"
        resolved_model = self._resolved_model()
        try:
            self.model = YOLO(str(resolved_model))
        except Exception as exc:
            raise DetectorUnavailableError(f"Could not load model {resolved_model}: {exc}") from exc
        self.name = f"Ultralytics YOLO ({resolved_model})"

    def detect(self, images: list[np.ndarray]) -> list[list[ObjectDetection]]:
        if self.model is None:
            raise RuntimeError("Detector.load() must be called before detect()")
        try:
            results = self.model.predict(
                source=images,
                conf=self.confidence,
                device=self.device,
                verbose=False,
            )
        except Exception as exc:
            raise DetectorUnavailableError(f"Object detection failed: {exc}") from exc
        output: list[list[ObjectDetection]] = []
        for result in results:
            detections: list[ObjectDetection] = []
            names = result.names
            for box in result.boxes:
                class_id = int(box.cls[0].item())
                class_name = str(names[class_id])
                coordinates = tuple(float(item) for item in box.xyxy[0].cpu().tolist())
                detections.append(
                    ObjectDetection(
                        class_name,
                        category_for(class_name),
                        float(box.conf[0].item()),
                        coordinates,  # type: ignore[arg-type]
                    )
                )
            output.append(detections)
        return output
