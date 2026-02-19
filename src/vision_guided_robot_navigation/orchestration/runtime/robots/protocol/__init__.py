# src/vision_guided_robot_navigation/orchestration/runtime/robots/protocol/__init__.py

from .register_maps import (
    PROTOCOL_VERSION,

    UNLOADER_NR_NUMBERS,
    UNLOADER_NR_VALUES,
    UNLOADER_SR_NUMBERS,
    UNLOADER_PR_NUMBERS,
    UNLOADER_ITERATION_NAMES,
)

__all__ = [
    # Protocol
    "PROTOCOL_VERSION",

    "UNLOADER_NR_NUMBERS",
    "UNLOADER_NR_VALUES",
    "UNLOADER_SR_NUMBERS",
    "UNLOADER_PR_NUMBERS",
    "UNLOADER_ITERATION_NAMES",
]