# src/vision_guided_robot_navigation/orchestration/runtime/robots/protocol/register_maps.py
from __future__ import annotations

from dataclasses import dataclass

PROTOCOL_VERSION = "robot_regs_v1"

# =======UNLOADER REGISTERS=======
@dataclass(frozen=True)
class UnloaderNRNumbers:
    iteration_starter: int = 1
    grip_status: int = 2
    move_status: int = 3

@dataclass(frozen=True)
class UnloaderNRValues:
    start: int = 1
    reset: int = 0
    end: int = 2
    grip_good: int = 2
    grip_bad: int = 3
    grip_reset: int = 0
    move_start: int = 1
    move_stop: int = 0

@dataclass(frozen=True)
class UnloaderSRNumbers:
    iteration_type: int = 1
    unloader_data: int = 2
    
@dataclass(frozen=True)
class UnloaderPRNumbers:
   tube_dump : int = 8

@dataclass(frozen=True)
class UnloaderSRValues:
    transfer: str = "TRANSFER_ITERATION"
    replacement: str = "REPLACEMENT_ITERATION"
    unloading: str = "UNLOAD_ITERATION"
    none: str = "NONE"


UNLOADER_NR_NUMBERS = UnloaderNRNumbers()
UNLOADER_NR_VALUES = UnloaderNRValues()
UNLOADER_SR_NUMBERS = UnloaderSRNumbers()
UNLOADER_PR_NUMBERS = UnloaderPRNumbers()
UNLOADER_ITERATION_NAMES = UnloaderSRValues()
