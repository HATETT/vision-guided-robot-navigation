# src/vision_guided_robot_navigation/orchestration/app/bootstrap.py
import threading
import logging
import time
from typing import Dict

from src.vision_guided_robot_navigation.config import load_alert_config
from src.vision_guided_robot_navigation.orchestration.app.shutdown import shutdown

from src.vision_guided_robot_navigation.logging import (
    create_logger, 
    install_global_exception_hooks,
)
from src.vision_guided_robot_navigation.config import (
    load_system_layout_config,
    load_unloader_config,
)
from src.vision_guided_robot_navigation.devices import (
    CellRobot,
    RobotAgilebot,
)
from src.vision_guided_robot_navigation.domain import (
    UnloadingTripod,
    LoadingTripod,
    Tripod,
    RackManager,
)
from src.vision_guided_robot_navigation.orchestration.runtime import ( 
    TripodRefresher,
    UnloaderRobotThread,

)

UNLOADER_CFG = load_unloader_config()
UNLOADER_SCANNER = UNLOADER_CFG.scanner


def build_loggers():
    logger_unloader = create_logger("ProjectR.Unloading", "unloader_robot.log")
    logger_system = create_logger("ProjectR.system", "system.log")

    return {
        "unloader": logger_unloader,
        "system": logger_system,
    }

def build_layout(logger: logging.Logger):
    cfg = load_system_layout_config()

    unloading_tripods = [
        UnloadingTripod(name=f"{i+1}") 
        for i in range(cfg.unloading_tripods)
    ]
    loading_tripods = [
        LoadingTripod(name=f"{i+1}") 
        for i in range(cfg.loading_tripods)
    ]

    rack_manager = RackManager(
        racks_in_loading_zone=cfg.racks_in_loading_zone,
        racks_in_unloading_zone=cfg.racks_in_unloading_zone,
    )

    logger.info(f"Система проиницилизированна с:" 
                f"\n{cfg.unloading_tripods} триподами Loader,"
                f"\n{cfg.loading_tripods} триподами Unloader,"
                f"\n{cfg.racks_in_loading_zone} рэками в зоне Loader,"
                f"\n{cfg.racks_in_unloading_zone} рэками в зоне Unloader."
    )

    return unloading_tripods, loading_tripods, rack_manager

def build_tripod_refresher(
    tripods: list[Tripod],
    thread_name: str,
    refresh_event: threading.Event,
    stop_event: threading.Event,
    logger: logging.Logger,
) -> tuple[Dict[str, Tripod], TripodRefresher]:
    """
    Строит словарь триподов и рефрешер для них.

    tripods - список объектов Tripod (LoadingTripod или UnloadingTripod)
    """
    tripod_map: Dict[str, Tripod] = {t.name: t for t in tripods}
    
    refresher = TripodRefresher(
        tripods=tripod_map,
        refresh_event=refresh_event,
        stop_event=stop_event,
        logger=logger,
    )
    
    refresher.name = thread_name
    refresher.start()

    return tripod_map, refresher


def run_workcell() -> None:
    # 0. Создаем объекты для управления потоками и логирования

    unloader_tripod_refresh_event = threading.Event()
    stop_event = threading.Event()

    loggers = build_loggers()
    install_global_exception_hooks()

    # 1. Поднимаем роботов и основные сенсоры
    try:
        unloader_robot = RobotAgilebot(name=UNLOADER_CFG.name, ip=UNLOADER_CFG.ip)
        unloader_robot.connect()
    except Exception:
        loggers["system"].info("Не удалось подключиться к роботу")

    # 2. Геометрия системы (штативы, рэки и т.д.)
    unloading_tripods_list, loading_tripods_list, rack_manager = build_layout(
        logger=loggers["system"]
    )

    # 3. оздаем потоки управления состояниями триподов
    unloader_tripods_by_name, unloader_tripod_thread = build_tripod_refresher(
        tripods=loading_tripods_list,
        thread_name="UnloaderTripodRefresher",
        refresh_event=unloader_tripod_refresh_event,
        stop_event=stop_event,
        logger=loggers["unloader"],
    )

    # 4. Поток робота
    unloader_thread = UnloaderRobotThread(
        unloader_robot=unloader_robot,
        unloader_cfg=UNLOADER_CFG,
        unloader_tripods=unloader_tripods_by_name,
        unloader_tripods_thread=unloader_tripod_thread,
        logger= loggers["unloader"],
        stop_event=stop_event,
    )

    unloader_thread.start()

    # 5. Собираем все потоки, которыми управляем
    threads: list[threading.Thread] = [
        unloader_tripod_thread,
        unloader_thread,
    ]

    # 6. Основной цикл / ожидание (пока просто живём)
    try:
        loggers["system"].info("Рабочая ячейка запущена")
        # Примитивный вариант: просто ждём, пока нас не убьют Ctrl+C
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        loggers["system"].info("Получен KeyboardInterrupt, инициируем остановку...")
    finally:
        # 7. Аккуратный shutdown
        shutdown(stop_event=stop_event, threads=threads, logger=loggers["system"])

        # Гасим робота
        try:
            unloader_robot.stop_all_running_programms()
            unloader_robot.disconnect()
        except Exception as e:
            loggers["system"].error(f"Ошибка при отключении: {e}")

        loggers["system"].info("run_workcell завершён")
