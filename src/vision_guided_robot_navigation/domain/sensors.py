# src/vision_guided_robot_navigation/domain/sensors.py
from dataclasses import dataclass
from enum import Enum
from typing import Literal


class RobotRole(str, Enum):
    LOADER = "loader"       # робот-загрузчик
    UNLOADER = "unloader"   # робот-выгрузчик


class SensorType(str, Enum):
    OPTICAL = "optical"  # оптический
    END = "end"          # концевик


@dataclass
class SensorConfig:
    """
    Описание одного булевого датчика на DI робота.
    value == True  -> датчик "сработал"
    value == False -> датчик "покоя"
    """
    name: str
    di_id: int
    robot_role: RobotRole
    sensor_type: SensorType
    active_high: bool = True  # True: 1 = сработал, False: 0 = сработал (на будущее)




# from mindray_automation_2.domain.sensors import RobotRole

# robots = {
#     RobotRole.LOADER: loader_robot,
#     RobotRole.UNLOADER: unloader_robot,
# }