# src/mindray_automation_2/orchestration/runtime/tripods/intefaces.py
from __future__ import annotations
from typing import Protocol

class TripodAvailabilityProvider(Protocol):
    def get_available_tripod_name(self) -> str | None:
        ...

class SensorReader(Protocol):
    def read(self, name: str) -> bool:
        ...