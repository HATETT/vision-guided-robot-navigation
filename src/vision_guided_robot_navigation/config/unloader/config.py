# src/vision_guided_robot_navigation/config/unloader/config.py
from dataclasses import dataclass
from pathlib import Path
import yaml


CONFIG_PATH = Path(__file__).with_name("unloader.yaml")

@dataclass(frozen=True)
class UnloaderScannerConfig:
    ip: str
    port: int
    name: str
    timeout: float

@dataclass(frozen=True)
class UnloaderConfig:
    ip: str                 # IP робота-загрузчика
    name: str               # имя робота (логическое)
    robot_program_name: str # имя программы на контроллере
    scanner: UnloaderScannerConfig

def load_unloader_config(path: Path | None = None) -> UnloaderConfig:
    cfg_path = path or CONFIG_PATH
    with cfg_path.open("r", encoding="utf-8") as f:
        raw = yaml.safe_load(f)

    unloader_raw = raw["unloader"]
    scanner_raw = unloader_raw["scanner"]

    scanner = UnloaderScannerConfig(
        ip=scanner_raw["ip"],
        port=int(scanner_raw["port"]),
        name=scanner_raw["name"],
        timeout=float(scanner_raw["timeout"]),
    )

    return UnloaderConfig(
        ip=unloader_raw["ip"],
        name=unloader_raw["name"],
        robot_program_name=unloader_raw["robot_program_name"],
        scanner=scanner,
    )
