# src/mindray_automation_2/orchestration/runtime/robots/protocol/register_maps.py
from __future__ import annotations

from dataclasses import dataclass

PROTOCOL_VERSION = "robot_regs_v1"

# =======LOADER REGISTERS=======
@dataclass(frozen=True)
class LoaderNRNumbers:
    iteration_starter: int = 1
    grip_status: int = 2
    scan_status: int = 3
    scan_delay: int = 4
    move_status: int = 5

@dataclass(frozen=True)
class LoaderNRValues:
    start: int = 1
    reset: int = 0
    end: int = 2
    grip_good: int = 1
    grip_bad: int = 2
    grip_reset: int = 0
    scan_good: int = 1
    scan_bad: int = 2
    scan_reset: int = 0
    delay_reset: float = 0.0
    move_start: int = 1
    move_stop: int = 0

@dataclass(frozen=True)
class LoaderSRNumbers:
    iteration_type: int = 1
    loader_data: int = 2
    
@dataclass(frozen=True)
class LoaderSRValues:
    loading: str = "LOAD_ITERATION"
    stacking: str = "STACK_ITERATION"
    none: str = "NONE"

LOADER_NR_NUMBERS = LoaderNRNumbers()
LOADER_NR_VALUES = LoaderNRValues()
LOADER_SR_NUMBERS = LoaderSRNumbers()
LOADER_ITERATION_NAMES = LoaderSRValues()

# =======UNLOADER REGISTERS=======
@dataclass(frozen=True)
class UnloaderNRNumbers:
    iteration_starter: int = 1
    grip_status: int = 2
    stack_rack: int = 3
    move_status: int = 4

@dataclass(frozen=True)
class UnloaderNRValues:
    start: int = 1
    reset: int = 0
    end: int = 2
    grip_good: int = 1
    grip_bad: int = 2
    grip_reset: int = 0
    stack_emergency = 1
    stack_normal = 0
    move_start: int = 1
    move_stop: int = 0

@dataclass(frozen=True)
class UnloaderSRNumbers:
    iteration_type: int = 1
    unloader_data: int = 2
    
@dataclass(frozen=True)
class UnloaderSRValues:
    transfer: str = "TRANSFER_ITERATION"
    replacement: str = "REPLACEMENT_ITERATION"
    unloading: str = "UNLOAD_ITERATION"
    none: str = "NONE"

UNLOADER_NR_NUMBERS = UnloaderNRNumbers()
UNLOADER_NR_VALUES = UnloaderNRValues()
UNLOADER_SR_NUMBERS = UnloaderSRNumbers()
UNLOADER_ITERATION_NAMES = UnloaderSRValues()