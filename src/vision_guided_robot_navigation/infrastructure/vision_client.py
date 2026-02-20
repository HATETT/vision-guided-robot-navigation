# src/vision_guided_robot_navigation/infrastructure/__init__.py
from __future__ import annotations
from dataclasses import dataclass
from typing import Any
import requests


@dataclass(frozen=True)
class TubeCoordinates:
    x: float
    y: float
    z: float
    a: float
    b: float
    c: float
    confidence: float | None = None

    def as_dict(self) -> dict[str, float]:
        # robot-код ждёт dict[str,float] строго по ключам:
        return {
            "x": float(self.x),
            "y": float(self.y),
            "z": float(self.z),
            "a": float(self.a),
            "b": float(self.b),
            "c": float(self.c),
        }

class VisionClient:
    def __init__(self, base_url: str, *, timeout_s: float = 2.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout_s = timeout_s

    def health(self) -> bool:
        r = requests.get(f"{self.base_url}/health", timeout=self.timeout_s)
        return r.status_code == 200

    def predict_from_file(self, image_path: str) -> TubeCoordinates | None:
        """
        ЛИНЕЙНО: отправляем файл, ждём ответ.
        Возвращаем None, если сервис не дал валидный результат.
        """
        with open(image_path, "rb") as f:
            files = {"image": ("frame.jpg", f, "image/jpeg")}
            r = requests.post(f"{self.base_url}/predict", files=files, timeout=self.timeout_s)

        if r.status_code != 200:
            return None

        data: dict[str, Any] = r.json()

        # минимальная валидация ключей
        for k in ("x", "y", "z", "a", "b", "c"):
            if k not in data:
                return None

        return TubeCoordinates(
            x=float(data["x"]),
            y=float(data["y"]),
            z=float(data["z"]),
            a=float(data["a"]),
            b=float(data["b"]),
            c=float(data["c"]),
            confidence=float(data["confidence"]) if "confidence" in data else None,
        )