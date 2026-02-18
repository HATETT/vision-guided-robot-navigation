# src/mindray_automation_2/orchestration/runtime/read_sensor.py
from __future__ import annotations
from src.mindray_automation_2.domain import SensorConfig, RobotRole
from src.mindray_automation_2.devices import CellRobot

def read_sensor(sensor: SensorConfig, robots: dict[RobotRole, CellRobot]) -> bool:
    """
    Возвращает логическое состояние датчика:
    True  -> датчик активен (луч перекрыт, объект есть)
    False -> датчик неактивен.
    """
    robot = robots[sensor.robot_role]
    return robot.get_DO(sensor.di_id)

