# src/vision_guided_robot_navigation/orchestration/runtime/robots/base_robot_thread.py
from __future__ import annotations

import threading
import time
import logging
from dataclasses import dataclass
from enum import Enum
from typing import Callable, TYPE_CHECKING, TypeVar
from src.vision_guided_robot_navigation.orchestration.runtime.robots.errors.iteration_exceptions import(
    IterationStopped,
    IterationTimeout,
    IterationAbort
)
if TYPE_CHECKING:
    from src.vision_guided_robot_navigation.devices import CellRobot
T = TypeVar("T")

@dataclass(frozen=True)
class IterationContext:
    """Параметры сброса/политики для конкретного робота."""
    robot: "CellRobot"
    starter_nr: int
    starter_reset: int

class GuardResult(Enum):
    OK = "ok"
    SKIP = "skip"      # timeout/abort → пропустить итерацию и продолжить главный цикл
    STOP = "stop"      # stopped → выйти из потока

class BaseRobotThread(threading.Thread):
    """
    Базовый поток для робот-логики.
    """

    def __init__(self, *args, stop_event: threading.Event, logger: logging.Logger, **kwargs):
        super().__init__(*args, **kwargs)
        self.stop_event = stop_event
        self.logger = logger

    def prepare_robot(self, robot: "CellRobot", program_name:str) -> None:
        """
        Подготовка робота к началу работы.
        - Останавливает исполнение всех программ
        - Сбрасывает все ошибки
        - Запускает программу с именем program_name
        """
        robot.stop_all_running_programms()
        robot.reset_errors()
        robot.start_program(program_name)

    def wait_until(
        self,
        condition: Callable[[], bool],
        *,
        timeout: float | None = None,
        poll: float = 0.1,
        reason: str = ""
    ):
        """
        Ждём выполнения condition().
        - timeout → IterationTimeout
        - stop_event → IterationStopped
        """
        start = time.monotonic()
        while True:
            if self.stop_event.is_set():
                raise IterationStopped(reason or "Остановка по stop_event")
            if condition():
                return
            if timeout is not None and (time.monotonic() - start) >= timeout:
                raise IterationTimeout(reason or "Таймаут ожидания")

            time.sleep(poll)

    # def reset_robot_iteration_state(self, robot: "CellRobot", iteration_starter_nr: int, iteration_starter_reset: int):
    #     """
    #     Метод для стандартного сброса типа итерации робота
    #     """
    #     robot.set_number_register(iteration_starter_nr, iteration_starter_reset)

    def reset_robot_iteration_state(self, ctx: IterationContext) -> None:
        """Метод для стандартного сброса типа итерации робота"""
        ctx.robot.set_number_register(ctx.starter_nr, ctx.starter_reset)

    def _execute_with_guard(self, 
            *, 
            name: str, 
            ctx: IterationContext, 
            fn: Callable[[], T]
        ) -> tuple[GuardResult, T | None]:
        """
        Унифицированный гард для итераций.
        Возвращает (статус, результат) чтобы run() мог лаконично решать что делать дальше.
        """
        try:
            return GuardResult.OK, fn()

        except IterationTimeout as e:
            self.logger.error(f"{name}: таймаут: {e}")
            self.reset_robot_iteration_state(ctx)
            return GuardResult.SKIP, None

        except IterationAbort as e:
            self.logger.warning(f"{name}: прервано: {e}")
            self.reset_robot_iteration_state(ctx)
            return GuardResult.SKIP, None

        except IterationStopped as e:
            self.logger.info(f"{name}: остановлено: {e}")
            self.reset_robot_iteration_state(ctx)
            return GuardResult.STOP, None