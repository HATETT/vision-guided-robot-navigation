# src/mindray_automation_2/orchestration/runtime/robots/__init__.py

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

    LOADER_NR_NUMBERS,
    LOADER_NR_VALUES,
    LOADER_SR_NUMBERS,
    LOADER_ITERATION_NAMES,

    UNLOADER_NR_NUMBERS,
    UNLOADER_NR_VALUES,
    UNLOADER_SR_NUMBERS,
    UNLOADER_ITERATION_NAMES,
)

from .loader_thread import LoaderRobotThread
from .unloader_thread import UnloaderRobotThread

from .errors import (
    IterationAbort,
    IterationTimeout,
    IterationStopped,
)

__all__ = [
    # Threads
    "BaseRobotThread",
    "LoaderRobotThread",
    "UnloaderRobotThread",

    # Iterations 
    "IterationContext",
    "GuardResult",

    # Protocol
    "PROTOCOL_VERSION",

    "LOADER_NR_NUMBERS",
    "LOADER_NR_VALUES",
    "LOADER_SR_NUMBERS",
    "LOADER_ITERATION_NAMES",

    "UNLOADER_NR_NUMBERS",
    "UNLOADER_NR_VALUES",
    "UNLOADER_SR_NUMBERS",
    "UNLOADER_ITERATION_NAMES",

    # Exceptions
    "IterationAbort",
    "IterationTimeout",
    "IterationStopped",
]

