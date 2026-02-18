# src/mindray_automation_2/config/__init__.py

"""
Публичный интерфейс загрузки конфигураций.
"""

from .sensors import load_sensors_config, SensorConfig, RobotRole, build_sensor_map, get_sensor
from .layout import load_system_layout_config
from .loader import load_loader_config, LoaderConfig
from .alert import load_alert_config
from .tower import load_tower_config
from .unloader import load_unloader_config

__all__ = (
    # sensors
    "load_sensors_config",
    "build_sensor_map",
    "get_sensor",
    "SensorConfig",
    "RobotRole",

    # layout
    "load_system_layout_config",

    # modules
    "load_loader_config",
    "LoaderConfig",
    "load_unloader_config",
    "UnloaderConfig",
    "load_tower_config",
    "load_alert_config",
)