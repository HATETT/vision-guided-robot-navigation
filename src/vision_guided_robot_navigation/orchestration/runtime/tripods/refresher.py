# src/vision_guided_robot_navigation/orchestration/runtime/tripods/refresher.py
import threading
import time
import logging
from typing import Dict

from src.vision_guided_robot_navigation.domain import Tripod, LoadingTripod, UnloadingTripod

class TripodRefresher(threading.Thread):
    """
    Поток обновления доступности триподов по команде оператора.

    Логика:
    - если Event поднят - пробуем обновить available у триподов
    - если нет триподов с .available = True - ставим им всем. available = True
    - если есть - запонимаем
    """
    
    def __init__(
            self,
            tripods: Dict[str, Tripod],
            refresh_event:threading.Event,
            stop_event:threading.Event,
            logger: logging.Logger,
    ):
        super().__init__(daemon=True)

        self.tripods = tripods
        self.refresh_event = refresh_event
        self.stop_event = stop_event
        self._last_refresh_state = False
        self.logger = logger

    def _refresh_tripod_availability(self):
        for name, tripod, in self.tripods.items():
            tripod.set_availability(True)
            self.logger.info(f"[{name}] Трипод стал доступен после операции обновления" )
        self._last_refresh_state = True

    def run(self) -> None:
        """Основной цикл потока."""
        while not self.stop_event.is_set():
            if self.refresh_event.is_set():
                try:
                    first_tripod = next(iter(self.tripods.values()))

                    # Штативы для выгрузки обновляются только при отсутствии доступных пробирок в них
                    if isinstance(first_tripod, LoadingTripod):
                        any_available = any(t.availability for t in self.tripods.values())
                        if any_available:
                            self._last_refresh_state = False
                            self.logger.info(f"Трипод все еще доступен, сброс отменен" )
                        else:
                            self._refresh_tripod_availability()

                    # Штативы для загрузки обновляются принудительно в любом случае
                    elif isinstance(first_tripod, UnloadingTripod):
                        self._refresh_tripod_availability()
                except Exception as e:
                    self._last_refresh_state = False
                    self.logger.critical(f"Во время обновления доступности штативов произошла критическая ошибка {e}")
                finally:
                    self.refresh_event.clear()
            time.sleep(0.3)

    def get_available_tripod_name(self) -> str | None:
        """
        Возвращает имя первого доступного трипода в системе 
        или None, если такого трипода нет.
        """
        for name, tripod in self.tripods.items():
            if  tripod.availability:
                return name
        return None

    def get_refresh_state(self) -> bool:
        """
        Возвращает статус посследней попытки обновления триподов.

        :return: bool
        """
        return self._last_refresh_state