# src/vision_guided_robot_navigation/orchestration/runtime/robots/__init__.py

"""
Логика исполнения роботизированных операций.

Содержит:
- базовый класс потоков роботов
- реализации потоков загрузчика и выгрузчика
- контракт протокола регистров (NR/SR)
- исключения итераций
"""

from .base_robot_thread import (
    BaseRobotThread, 
    IterationContext, 
    GuardResult,
)

from .protocol import (
    PROTOCOL_VERSION,

    UNLOADER_NR_NUMBERS,
    UNLOADER_NR_VALUES,
    UNLOADER_SR_NUMBERS,
    UNLOADER_ITERATION_NAMES,
)

from .unloader_thread import UnloaderRobotThread

from .errors import (
    IterationAbort,
    IterationTimeout,
    IterationStopped,
)

__all__ = [
    # Threads
    "BaseRobotThread",
    "UnloaderRobotThread",

    # Iterations 
    "IterationContext",
    "GuardResult",

    # Protocol
    "PROTOCOL_VERSION",

    "UNLOADER_NR_NUMBERS",
    "UNLOADER_NR_VALUES",
    "UNLOADER_SR_NUMBERS",
    "UNLOADER_ITERATION_NAMES",

    # Exceptions
    "IterationAbort",
    "IterationTimeout",
    "IterationStopped",
]

