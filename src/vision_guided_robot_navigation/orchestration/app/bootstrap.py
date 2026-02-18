# src/mindray_automation_2/orchestration/app/bootstrap.py
import threading
import logging
import time
from typing import Dict


from src.mindray_automation_2.orchestration.app.gui.app import run_gui
from src.mindray_automation_2.orchestration.app.gui.context import AppContext

from src.mindray_automation_2.config import load_alert_config
from src.mindray_automation_2.orchestration.app.shutdown import shutdown
from src.mindray_automation_2.alerting import (
    AlarmManager, 
    TelegramClient, 
    LogManager
) 
from src.mindray_automation_2.logging import (
    create_logger, 
    install_global_exception_hooks,
)
from src.mindray_automation_2.config import (
    load_sensors_config, 
    SensorConfig, RobotRole, 
    load_system_layout_config,
    load_loader_config,
    load_unloader_config,
    build_sensor_map,
    load_tower_config,
)
from src.mindray_automation_2.devices import (
    CellRobot,
    RobotAgilebot,
    ScannerHikrobotTCP,
)
from src.mindray_automation_2.domain import (
    UnloadingTripod,
    LoadingTripod,
    Tripod,
    RackManager,
)
from src.mindray_automation_2.tower import (
    TowerStateStore,
    DummyTowerDriver,
    TowerDoMap,
    RoborSignalTowerDriver,
    SignalTowerWorkerThread
)
from src.mindray_automation_2.orchestration.runtime import ( 
    read_sensor, 
    SensorAccess,
    TripodMonitor,
    TripodRefresher,
    UnloaderRobotThread,
    LoaderRobotThread
)


ALERT_CFG = load_alert_config()
LOADER_CFG = load_loader_config()
LOADER_SCANNER = LOADER_CFG.scanner
UNLOADER_CFG = load_unloader_config()
UNLOADER_SCANNER = UNLOADER_CFG.scanner


def build_loggers():
    logger_loader = create_logger("ProjectR.Loading", "loader_robot.log")
    logger_unloader = create_logger("ProjectR.Unloading", "unloader_robot.log")
    logger_tower = create_logger("ProjectR.Tower", "tower.log")
    logger_gui = create_logger("ProjectR.gui", "gui.log")
    logger_system = create_logger("ProjectR.system", "system.log")

    return {
        "loader": logger_loader,
        "unloader": logger_unloader,
        "tower": logger_tower,
        "gui": logger_gui,
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


def build_tripod_monitor(
    tripods: list[Tripod],
    sensor_prefix: str,
    robots: Dict[RobotRole, CellRobot],
    logger: logging.Logger,
    thread_name: str,
    stop_event: threading.Event,
    debounce_seconds: float = 2.0,
    poll_interval: float = 0.1,
) -> tuple[Dict[str, Tripod], TripodMonitor]:
    """
    Строит словарь триподов и монитор для них.

    tripods       - список объектов Tripod (LoadingTripod или UnloadingTripod)
    sensor_prefix - префикс имени датчиков из sensors.yaml, например:
                    "loader_pallet_" или "unloader_pallet_"
    """
    # превращаем список триподов в словарь по имени: "1" -> tripod
    tripod_map: Dict[str, Tripod] = {t.name: t for t in tripods}

    all_sensors = load_sensors_config()
    tripod_sensors: Dict[str, SensorConfig] = {}

    for sensor in all_sensors:
        if sensor.name.startswith(sensor_prefix):
            # loader_pallet_1_present -> ["loader", "pallet", "1", "present"]
            parts = sensor.name.split("_")
            if len(parts) >= 3:
                tripod_name = parts[2]   # "1", "2", "3", ...
                if tripod_name in tripod_map:
                    tripod_sensors[tripod_name] = sensor

    monitor = TripodMonitor(
        tripods=tripod_map,
        tripod_sensors=tripod_sensors,
        robots=robots,
        logger=logger,
        stop_event=stop_event,
        debounce_seconds=debounce_seconds,
        poll_interval=poll_interval,
    )
    monitor.name = thread_name
    monitor.daemon = True
    monitor.start()

    return tripod_map, monitor

def build_tower(
    robots: dict[RobotRole, CellRobot],
    stop_event: threading.Event,
    logger: logging.Logger,
):
    cfg = load_tower_config()

    store = TowerStateStore()

    if cfg.driver == "dummy":
        driver = DummyTowerDriver()
    else:
        role = RobotRole[cfg.robot_role.upper()]
        robot = robots[role]
        do_map = TowerDoMap(
            orange=cfg.do_map.orange,
            green=cfg.do_map.green,
            white=cfg.do_map.white,
            buzzer=cfg.do_map.buzzer,
        )
        driver = RoborSignalTowerDriver(robot, do_map)

    worker = SignalTowerWorkerThread(store=store, driver=driver, stop_event=stop_event, logger=logger)
    worker.start()
    return store, worker

def run_workcell(based_on_sensors: bool = False) -> None:
    # 0. Создаем объекты для управления потоками и логирования
    if not based_on_sensors:
        loader_tripod_refresh_event = threading.Event()
        unloader_tripod_refresh_event = threading.Event()
    stop_event = threading.Event()
    run_event = threading.Event()

    loggers = build_loggers()
    install_global_exception_hooks()



    # 1. Поднимаем роботов и основные сенсоры
    # try:
    #     loader_robot = RobotAgilebot(name=LOADER_CFG.name, ip=LOADER_CFG.ip)
    #     loader_scanner = ScannerHikrobotTCP(
    #         name=LOADER_SCANNER.name, 
    #         ip=LOADER_SCANNER.ip, 
    #         port=LOADER_SCANNER.port
    #     )

    #     unloader_robot = RobotAgilebot(name=UNLOADER_CFG.name, ip=UNLOADER_CFG.ip)
    #     unloader_scanner = ScannerHikrobotTCP(
    #         name=UNLOADER_SCANNER.name, 
    #         ip=UNLOADER_SCANNER.ip, 
    #         port=UNLOADER_SCANNER.port
    #     )

    #     loader_robot.connect()
    #     loader_scanner.connect()
    #     unloader_robot.connect()
    #     unloader_scanner.connect()

    #     robots: dict[RobotRole, CellRobot] = {
    #         RobotRole.LOADER: loader_robot,
    #         RobotRole.UNLOADER: unloader_robot,
    #     }
    # except Exception:
    loader_robot = object()
    unloader_robot = object()
    loader_scanner = object()
    unloader_scanner = object()
    robots: dict[RobotRole, CellRobot] = {
        RobotRole.LOADER: loader_robot,
        RobotRole.UNLOADER: unloader_robot,
    }

    sensor_map = build_sensor_map()
    sensor_access = SensorAccess(
    reader=lambda name: read_sensor(sensor_map[name], robots)
    )

    # 2. Инициализация alerting
    if ALERT_CFG.telegram.enabled:
        tg_client = TelegramClient(
            token=ALERT_CFG.telegram.token,
            chat_id=ALERT_CFG.telegram.chat_id,
        )
    else:
        tg_client = None

    log_manager = LogManager()   # или LogManager(logs_dir=LOG_DIR)

    alarms_manager = AlarmManager(
        system_name=ALERT_CFG.system_name,
        stop_event=stop_event,
        telegram_client=tg_client,
        log_manager=log_manager,
    )
    alarms_manager.start()
    # alarms_manager.send_test_message()

    # 3. Геометрия системы (штативы, рэки и т.д.)
    unloading_tripods_list, loading_tripods_list, rack_manager = build_layout(
        logger=loggers["system"]
    )

    # 4. оздаем потоки управления состояниями триподов
    if based_on_sensors:
        # 4.1. Если система определяет триподы автоматически
        # Монитор триподов для первого робота (loader)
        loader_tripods_by_name, loader_tripod_thread = build_tripod_monitor(
            tripods=unloading_tripods_list,
            sensor_prefix="loader_pallet_",
            robots=robots,
            logger=loggers["loader"],
            thread_name="LoaderTripodMonitor",
            stop_event=stop_event
        )

        # Монитор триподов для второго робота (unloader)
        unloader_tripods_by_name, unloader_tripod_thread = build_tripod_monitor(
            tripods=loading_tripods_list,
            sensor_prefix="unloader_pallet_",
            robots=robots,
            logger=loggers["unloader"],
            thread_name="UnloaderTripodMonitor",
            stop_event=stop_event
        )
    else:
        # 4.1. Если система НЕ определяет триподы автоматически
        # Рефрешер триподов для первого робота (loader)
        loader_tripods_by_name, loader_tripod_thread = build_tripod_refresher(
            tripods=unloading_tripods_list,
            thread_name="LoaderTripodRefresher",
            refresh_event=loader_tripod_refresh_event,
            stop_event=stop_event,
            logger=loggers["loader"],
        )

        # Рефрешер триподов для второго робота (unloader)
        unloader_tripods_by_name, unloader_tripod_thread = build_tripod_refresher(
            tripods=loading_tripods_list,
            thread_name="UnloaderTripodRefresher",
            refresh_event=unloader_tripod_refresh_event,
            stop_event=stop_event,
            logger=loggers["unloader"],
        )


    # 6. Тестовое наблюдение (чисто для дебага)
    # import time
    # alarms_manager.trigger_alarm("CRITICAL LOADER ERROR", "test1")

    # 8. Поток сигнальной башни
    # tower_state_store, tower_thread = build_tower(
    #     robots=robots,
    #     stop_event=stop_event,
    #     logger=loggers["tower"]
    # )

    # # 7. Потоки роботов
    # loader_thread = LoaderRobotThread(
    #     rack_manager=rack_manager,
    #     loader_robot=loader_robot,
    #     loader_scanner=loader_scanner,
    #     loader_cfg=LOADER_CFG,
    #     loader_tripods=loader_tripods_by_name,
    #     unloader_tripods=unloader_tripods_by_name,
    #     tower_state_store=tower_state_store,
    #     loader_tripods_thread=loader_tripod_thread,
    #     logger= loggers["loader"],
    #     stop_event=stop_event,
    # )

    # unloader_thread = UnloaderRobotThread(
    #     rack_manager=rack_manager,
    #     sensor_access=sensor_access,
    #     unloader_robot=unloader_robot,
    #     unloader_scanner=unloader_scanner,
    #     unloader_cfg=UNLOADER_CFG,
    #     unloader_tripods=unloader_tripods_by_name,
    #     tower_state_store=tower_state_store,
    #     unloader_tripods_thread=unloader_tripod_thread,
    #     logger= loggers["unloader"],
    #     stop_event=stop_event,
    # )

    # loader_thread.start()
    # unloader_thread.start()

    # 8. Собираем все потоки, которыми управляем
    threads: list[threading.Thread] = [
        loader_tripod_thread,
        unloader_tripod_thread,
        # loader_thread,
        # unloader_thread,
        # tower_thread,
    ]

    from src.mindray_automation_2.orchestration.app.gui.utils.mock_robot import MockRobot


    # for tripod in unloader_tripods_by_name.values():
    #     tripod.set_availability(True)
    #     tripod.set_tubes(Tripod.MAX_TUBES)



    ctx = AppContext(
        stop_event=stop_event,
        run_event=run_event,
        logger=loggers["gui"],
        alarms=alarms_manager if "alarms_manager" in locals() else None,
        threads=threads,
        loader_tripods_by_name=loader_tripods_by_name if "loader_tripods_by_name" in locals() else None,
        unloader_tripods_by_name=unloader_tripods_by_name if "unloader_tripods_by_name" in locals() else None,
        rack_manager=rack_manager,
        loader_robot=loader_robot,
        unloader_robot=unloader_robot,
        loader_scanner=loader_scanner,
        unloader_scanner=unloader_scanner,
    )

    ctx.loader_robot = MockRobot("loader", initial_state="RUNNING")
    ctx.unloader_robot = MockRobot("unloader", initial_state="RUNNING")


    # GUI запускается в main thread и блокирует поток.
    run_gui(ctx)

    # После закрытия окна — инициируем остановку и выходим к finally.
    stop_event.set()
    return

    # # 9. Основной цикл / ожидание (пока просто живём)
    # try:
    #     loggers["system"].info("Рабочая ячейка запущена")
    #     # Примитивный вариант: просто ждём, пока нас не убьют Ctrl+C
    #     while True:
    #         time.sleep(1)
    # except KeyboardInterrupt:
    #     loggers["system"].info("Получен KeyboardInterrupt, инициируем остановку...")
    # finally:
    #     # 10. Аккуратный shutdown
    #     shutdown(stop_event=stop_event, threads=threads, logger=loggers["system"])

    #     # Гасим роботов/сканеры
    #     try:
    #         loader_robot.stop_all_running_programms()
    #         loader_robot.disconnect()
    #         loader_scanner.disconnect()
    #         unloader_robot.stop_all_running_programms()
    #         unloader_robot.disconnect()
    #         unloader_scanner.disconnect()
    #     except Exception as e:
    #         loggers["system"].error(f"Ошибка при отключении: {e}")

    #     loggers["system"].info("run_workcell завершён")
