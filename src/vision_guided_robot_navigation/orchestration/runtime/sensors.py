# src/mindray_automation_2/orchestration/runtime/sensors.py
from typing import Callable

class SensorAccess:
    def __init__(self, reader: Callable[[str], bool]):
        self._reader = reader

    def read(self, name: str) -> bool:
        return self._reader(name)
