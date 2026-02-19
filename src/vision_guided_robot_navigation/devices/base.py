# src/vision_guided_robot_navigation/devices/base.py
from abc import ABC, abstractmethod

class DeviceError(Exception):
    """Базовое исключение для всех устройств."""

class ConnectionError(DeviceError):
    """Ошибка подключения к устройству."""

class Robot(ABC):
    """Базовый робот: подключение и программы."""
    @abstractmethod
    def connect(self) -> None: ...
    @abstractmethod
    def disconnect(self) -> None: ...
    @abstractmethod
    def is_connected(self) -> bool: ...
    @abstractmethod
    def start_program(self, program_name: str) -> None: ...
    @abstractmethod
    def stop_program(self, program_name: str) -> None: ...
    @abstractmethod
    def stop_all_running_programms(self) -> None: ...
    @abstractmethod
    def reset_errors(self) -> None: ...


class RobotIO(ABC):
    """Интерфейс для робота с цифровыми входами/выходами."""
    @abstractmethod
    def get_DI(self, di_id: int) -> bool: ...
    @abstractmethod
    def get_DO(self, do_id: int) -> bool: ...
    @abstractmethod
    def set_DO(self, do_id: int, value: bool) -> None: ...


class RobotRegisters(ABC):
    """Интерфейс для робота с регистрами."""
    @abstractmethod
    def get_string_register(self, register_id: int) -> str: ...
    @abstractmethod
    def set_string_register(self, register_id: int, value: str) -> None: ...
    @abstractmethod
    def get_number_register(self, register_id: int) -> int | float: ...
    @abstractmethod
    def set_number_register(self, register_id: int, value: int | float) -> None: ...
    @abstractmethod
    def set_pose_register(self, pr_id: int, x_val: int | float, y_val: int | float, z_val: int | float, a_val: int | float, b_val: int | float, c_val: int | float) -> None: ...


class CellRobot(Robot, RobotIO, RobotRegisters, ABC):
    """Робот, подходящий для нашей автоматизированной ячейки."""
    pass
