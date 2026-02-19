# src/vision_guided_robot_navigation/orchestration/runtime/tripods/monitor.py
from __future__ import annotations

import threading
import time
import logging
from typing import Dict

from src.vision_guided_robot_navigation.domain import Tripod, SensorConfig, RobotRole
from src.vision_guided_robot_navigation.devices import CellRobot
from src.vision_guided_robot_navigation.orchestration.runtime import read_sensor

class TripodMonitor(threading.Thread):
    """
    Поток мониторинга триподов.

    Логика:
    - если датчик трипода == False -> сразу tripod.set_availability(False)
    - если датчик стал True и держится >= debounce_seconds -> tripod.set_availability(True)
    """

    def __init__(
        self,
        tripods: Dict[str, Tripod],
        tripod_sensors: Dict[str, SensorConfig],
        robots: Dict[RobotRole, CellRobot],
        logger: logging.Logger,
        stop_event: threading.Event,
        debounce_seconds: float = 2.0,
        poll_interval: float = 0.1,
    ):
        super().__init__(daemon=True)
        self.tripods = tripods                  # ключ = имя трипода ("1", "2", ...)
        self.tripod_sensors = tripod_sensors    # ключ = то же имя трипода
        self.robots = robots
        self.logger = logger
        self.debounce_seconds = debounce_seconds
        self.poll_interval = poll_interval
        self._selected_tripod: str | None = None # текущий "закреплённый" трипод

        # Предыдущее состояние датчика: None = ещё не знаем
        self._last_state: Dict[str, bool | None] = {
            name: None for name in self.tripods.keys()
        }

        self.stop_event = stop_event

        # Время, с которого сигнал по триподам стабильно True
        self._stable_since: Dict[str, float | None] = {
            name: None for name in self.tripods.keys()
        }

    def _update_tripod_from_sensor(self, name: str, tripod: Tripod, sensor: SensorConfig) -> None:
        raw_state = read_sensor(sensor, self.robots)  # True / False
        prev_state = self._last_state[name]

        # Первый запуск: просто запомнили состояние и ничего не делаем
        if prev_state is None:
            self._last_state[name] = raw_state
            # Если хочешь, можно здесь сразу сбросить трипод,
            # чтобы гарантировать "старт с нуля":
            if raw_state is False:
                tripod.set_tubes(Tripod.MIN_TUBES)
                tripod.set_availability(False)
            return

        # -------- СИГНАЛ 0 (False) --------
        if not raw_state:
            # Моментальный сброс доступности
            if tripod.availability or tripod.get_tubes() != Tripod.MIN_TUBES:
                tripod.set_tubes(Tripod.MIN_TUBES)
                tripod.set_availability(False)
                self.logger.info(f"[{name}] Трипод недоступен (датчик False)")

            # сбрасываем таймер устойчивого True
            self._stable_since[name] = None

            # если этот трипод был выбран — отжимаем
            if self._selected_tripod == name:
                self._selected_tripod = None

            self._last_state[name] = raw_state
            return

        # -------- СИГНАЛ 1 (True) --------
        now = time.perf_counter()

        # Обнаружили переход 0 → 1: начинаем отсчёт debounce
        if prev_state is False and raw_state is True:
            self._stable_since[name] = now
            self._last_state[name] = raw_state
            return

        # Если раньше не фиксировали 0→1 — игнорируем текущий True
        if self._stable_since[name] is None:
            self._last_state[name] = raw_state
            return

        # Проверяем, сколько времени держится True после перехода 0→1
        if (now - self._stable_since[name]) >= self.debounce_seconds:
            if not tripod.availability:
                tripod.set_availability(True)
                self.logger.info(
                    f"[{name}] Трипод стал доступен после {self.debounce_seconds} с устойчивого сигнала (после перехода 0→1)"
                )

        self._last_state[name] = raw_state

    def run(self) -> None:
        """Основной цикл потока."""
        self.logger.info(f"Поток [{threading.current_thread().name}] запущен")
        try:
            while not self.stop_event.is_set():
                for name, tripod in self.tripods.items():
                    sensor = self.tripod_sensors.get(name)
                    if sensor is None:
                        continue  # нет датчика для этого трипода

                    try:
                        self._update_tripod_from_sensor(name, tripod, sensor)
                    except Exception as e:
                        self.logger.error(f"[{name}] Ошибка при обновлении трипода: {e}")

                time.sleep(self.poll_interval)
        finally:
            self.logger.info(f"Поток [{threading.current_thread().name}] остановлен")

    def get_available_tripod_name(self) -> str | None:
        """
        Возвращает "закреплённый" трипод, если он ещё доступен.
        Если нет выбранного или выбранный стал недоступен — выбирает новый.
        """
        # 1) если уже есть выбранный и он всё ещё доступен — держимся за него
        if self._selected_tripod is not None:
            tripod = self.tripods.get(self._selected_tripod)
            if tripod is not None and tripod.availability:
                return self._selected_tripod
            # если он пропал/стал недоступен — освобождаем
            self._selected_tripod = None

        # 2) ищем первый доступный трипод и закрепляем его
        for name, tripod in self.tripods.items():
            if tripod.availability:
                self._selected_tripod = name
                return name

        # 3) вообще нет доступных триподов
        return None
