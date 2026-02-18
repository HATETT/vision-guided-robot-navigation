# src/mindray_automation_2/orchestration/runtime/robots/unloader_thread.py
import time
import logging
import threading


from src.mindray_automation_2.orchestration.runtime.robots.base_robot_thread import BaseRobotThread, IterationContext, GuardResult
from src.mindray_automation_2.devices import CellRobot, Scanner
from src.mindray_automation_2.tower import TowerStateStore
from src.mindray_automation_2.config.unloader.config import UnloaderConfig
from src.mindray_automation_2.orchestration.runtime.tripods import TripodAvailabilityProvider
from src.mindray_automation_2.orchestration.runtime import SensorAccess
from src.mindray_automation_2.orchestration.runtime.robots.protocol import (
    UNLOADER_NR_NUMBERS,
    UNLOADER_NR_VALUES,
    UNLOADER_SR_NUMBERS,
    UNLOADER_ITERATION_NAMES,
)
from src.mindray_automation_2.domain import (
    RackManager,
    RACK_SAFE_DISTANCE,
    LoadingTripod, 
    RackOccupancy,
)

class UnloaderRobotThread(BaseRobotThread):
    """
    Поток, выполняющий основную логику робота-выгрузчика.

    Остановка: через stop_event (threading.Event).
    Пока stop_event не выставлен, поток крутит свой цикл.
    """

    def __init__(
        self,
        rack_manager: RackManager,
        sensor_access: SensorAccess,
        unloader_robot: CellRobot,
        unloader_scanner: Scanner,
        unloader_cfg: UnloaderConfig,
        unloader_tripods: dict[str, LoadingTripod],   # в эти штативы пробирки ставятся
        tower_state_store: TowerStateStore,
        unloader_tripods_thread: TripodAvailabilityProvider,
        logger: logging.Logger,
        stop_event: threading.Event,
    ) -> None:
        super().__init__(name="UnloaderRobotThread", daemon=True, stop_event=stop_event, logger=logger)
        self.rack_manager = rack_manager
        self.sensor_access = sensor_access
        self.unloader_robot = unloader_robot
        self.unloader_scanner = unloader_scanner
        self.unloader_tripods = unloader_tripods
        self.tower_state_store = tower_state_store
        self.unloader_tripods_thread = unloader_tripods_thread
        self.cfg = unloader_cfg
        self.scanner_cfg = self.cfg.scanner
        
    def _sensor(self, name: str) -> bool:
        """
        Возвращает значение сенсора по имени.
        """
        return self.sensor_access.read(name)
    
    def _set_tower_flag_value(self, *, value: bool, flag: str) -> None:
        """
        Устанавливаает статус наличия для отображения на сигнальной башне.
        """
        self.tower_state_store.update(**{flag: value})

    def _set_tower_missing(self, *, present: bool, missing_flag: str) -> None:
        """
        Устанавливаает отсутствия для отображения на сигнальной башне.
        """
        self.tower_state_store.update(**{missing_flag: not present})

    def _iteration_unloading(self, *, unloader_available_tripod: str | None, rack_number:str) -> None:
        """
        Выполняет логику итерации выгрузки пробирок из
        рэков в зоне выгрузки в штативы (триподы) выгрузки.
        
        :param unloader_available_tripod: Доступный трипод для загрузки в него пробирки
        :type unloader_available_tripod: str | None
        :param rack_number: Номер рэка, из которого можно выгружать пробирки
        :type rack_number: str
        """

        if not unloader_available_tripod:
            self.unloader_robot.set_string_register(UNLOADER_SR_NUMBERS.iteration_type, UNLOADER_ITERATION_NAMES.none)
            self.logger.warning("Штатив был убран во время работы установки")
            return

        # 3.1. В цикле разбираем рэка, пока не закончатся пробирки в нем
        for tube in reversed(range(self.rack_manager.get_rack_tube_count(rack_number))):
            self.logger.info("\n ====UNLOAD ITERATION====\n")
            self.unloader_robot.set_string_register(UNLOADER_SR_NUMBERS.iteration_type, UNLOADER_ITERATION_NAMES.unloading)

            # 3.2 Проверяем, не нужжно ли переключиться на более важную задачу
            unloader_available_tripod = self.unloader_tripods_thread.get_available_tripod_name()    # Проверям, естоь ли доступные штативы
            rack_out = self._sensor("mindray_rack_out_present")                                     # Проверяем, не выехал ли рэк из миндрея
            table_in = self._sensor("unloader_table_present")
            emergency_rack_out = self._sensor("emergency_rack_present")                             # Проверяем, задвинут ли столик
            self._set_tower_missing(present=table_in, missing_flag="unloader_table_missing")        # Устанавливаем башню по статусу столика
            self._set_tower_flag_value(value=emergency_rack_out, flag="emergency_rack_out")         # Устанавливаем башню по наличию экстренного рэка
            if rack_out:
                self.logger.warning("Из Mindray вышел рэк, прерываем итерацию выгрузки!")
                return
            elif not table_in:
                self.logger.warning("Стол не обнаружен, прерываем итерацию выгрузки!")
                return
            elif not unloader_available_tripod:
                self.logger.warning("Штатив для выгрузки не обнаружен прерываем итерацию выгрузки!")
                return

            # 3.3. Определяем точки назначения робота

            rack_tube_number = tube
            tripod_number = int(unloader_available_tripod)
            tripod_place_number = self.unloader_tripods[unloader_available_tripod].get_tubes()
            data_str = (                                                                            # Формируем пакет данных в виде строки роботу
                f"{int(rack_number):02d} "
                f"{rack_tube_number:02d} "
                f"{tripod_number:02d} "
                f"{tripod_place_number:02d}"
            )
            self.rack_manager.occupy_racks_by_robot(                                                # Окуупируем ближайшие рэки                                              
                position=rack_number, 
                busyness=RackOccupancy.BUSY_UNLOADER, 
                release=False, 
                logger=self.logger
            )
            self.unloader_robot.set_string_register(UNLOADER_SR_NUMBERS.unloader_data, data_str)     # Отправляем роботу строку с данными

            try:
                # 3.3. Стартуем итерацию после отправки всех данных роботу
                self.unloader_robot.set_number_register(UNLOADER_NR_NUMBERS.iteration_starter, UNLOADER_NR_VALUES.start)
                self.logger.info(f"Отдана команда на исполнение итерации {UNLOADER_ITERATION_NAMES.unloading}!") 

                # 3.4. Ждем пока робот физически уберет пробирку из рэка
                self.logger.info(f"Ожидание извлечения пробирки из рэка...") 
                self.wait_until(
                    lambda: self.unloader_robot.get_number_register(
                        UNLOADER_NR_NUMBERS.grip_status
                    ) == UNLOADER_NR_VALUES.grip_good,
                    timeout=10.0,
                    reason="Ожидание grip_status == grip_good"
                )
                self.logger.info(f"Пробирка {rack_tube_number} из рэка {rack_number} успешно извлечена")
                self.rack_manager.remove_tube_from_rack(rack_number)        # Убираем пробирку из рэка

                # 3.5. Ждем пока робот физически поставит пробирку в трипод
                self.logger.info(f"Ожидание установки пробирки в штатив...")
                self.wait_until(
                    lambda: self.unloader_robot.get_number_register(
                        UNLOADER_NR_NUMBERS.grip_status
                    )
                    == UNLOADER_NR_VALUES.grip_bad,
                    timeout=10.0,
                    reason="Ожидание grip_status == grip_bad"
                )
                self.logger.info(f"Пробирка успешно установлена в штатив {tripod_number} в позицию {tripod_place_number}")
                self.unloader_tripods[unloader_available_tripod].place_tube() # Устанавливаем пробирку в трипод

                # 3.7. Ждем инофрмации о завершении итерации роботом
                self.logger.info(f"Ожидание команды на завершение итерации...")
                self.wait_until(
                    lambda: self.unloader_robot.get_number_register(
                        UNLOADER_NR_NUMBERS.iteration_starter
                    )
                    == UNLOADER_NR_VALUES.end,
                    timeout=10.0,
                    reason="Ожидание iteration_starter == end"
                )
                self.logger.info(f"Команда на завершение итерации получена!")

                #Проверка - не выехал ли рэк, не закончилось ли место? не отвалился ли стол?
                # available, tripod_name = loading_tripods_thread.available_tipod_name
                # if available:
                #     #Для продолжения цикла разгрузки рэка устанавливаем тип итерации после его обнуления роботом
                #     unloading_robot.set_string_register(UNLOADER_SR_NUMBERS.iteration_type, "UNLOADING_ITERATION")
                # else:
                #     unloading_robot.set_string_register(UNLOADER_SR_NUMBERS.iteration_type, "NONE")
        
                # 3.8. Логируем состояние рэка и штатива по окночанию итерации
                self.rack_manager.log_rack_info(rack_number, self.logger)
                self.logger.info(self.unloader_tripods[unloader_available_tripod])

            finally:
                # 3.9. Возваращем стутус "FREE" ранее оккупированным рэкам
                self.rack_manager.occupy_racks_by_robot(
                    position=rack_number, 
                    busyness=RackOccupancy.BUSY_UNLOADER, 
                    release=True, 
                    logger=self.logger
                )

    def _iteration_transfer(self) -> None:
        """
        Выполняет логику итерации забора
        рэка из миндрея, его определения и постановки.
        """

        # 4.0 Объявляем итерацию
        self.logger.info("\n ====TRANSFER ITERATION====\n")
        self.unloader_robot.set_string_register(UNLOADER_SR_NUMBERS.iteration_type, UNLOADER_ITERATION_NAMES.transfer)

        # 4.2. Определяем судьбу рэка 
        barcode, _ = self.unloader_scanner.scan(timeout=self.scanner_cfg.timeout)
        rack_existance_in_system = self.rack_manager.find_rack_by_barcode(barcode)  # Определяем - наш рэк или нет
        occupied_position: str | None = None

        if not rack_existance_in_system:
            self.logger.warning("Прибыл эктренный рэк!")
            data_str = (                                                                            # Формируем пакет данных в виде строки роботу
                f"{int(UNLOADER_NR_VALUES.stack_emergency):02d}"
            )
        else:
            self.logger.info("Прибыл обработанный рэк!")
            data_str = (                                                                            # Формируем пакет данных в виде строки роботу
                f"{int(UNLOADER_NR_VALUES.stack_normal):02d}"
            )
            pass
        self.unloader_robot.set_string_register(UNLOADER_SR_NUMBERS.unloader_data, data_str)

        # 4.1. Стартуем итерацию только полсе получения данных о прибытии рэка
        self.unloader_robot.set_number_register(UNLOADER_NR_NUMBERS.iteration_starter, UNLOADER_NR_VALUES.start)
        self.logger.info(f"Отдана команда на исполнение итерации {UNLOADER_ITERATION_NAMES.transfer}!")

        # # 4.2. Определяем судьбу рэка 
        # barcode, _ = self.unloader_scanner.scan(timeout=self.scanner_cfg.timeout)
        # rack_existance_in_system = self.rack_manager.find_rack_by_barcode(barcode)  # Определяем - наш рэк или нет
        # occupied_position: str | None = None
        
        try:
            # 4.2.1 Рэк экстернный
            if not rack_existance_in_system:
                self.logger.warning("Обнаружен эктренный рэк!")
                # self.unloader_robot.set_number_register(UNLOADER_NR_NUMBERS.stack_rack, UNLOADER_NR_VALUES.stack_emergency) # Меняем точку назначения на точку для экстренного рэка
                # 4.2.1.1. Проверяем наличие второго экстренного рэка в системе во избежание столкновения
                if (self._sensor("emergency_rack_present") or not self._sensor("unloader_table_present")) :
                    self.unloader_robot.set_number_register(UNLOADER_NR_NUMBERS.move_status, UNLOADER_NR_VALUES.move_stop)
                    self.wait_until(
                        lambda: (
                            not self._sensor("emergency_rack_present")
                            and self._sensor("unloader_table_present")
                        ),
                        timeout=30.0,
                        reason="Ожидание освобождения зоны экстренного рэка"
                    )
                    self.unloader_robot.set_number_register(UNLOADER_NR_NUMBERS.move_status, UNLOADER_NR_VALUES.move_start)

            # Очень важно ставить рэк трансфером из миндрея в такое место в зоне выгрузки, 
            # в котором бы не произошло коллизии двух роботов, для этого идет работа со статусами рэков.
            # Находится первый оккупирвоанный рэк в зоне загрузки, от него отсчитывается 
            # заданное в конфиге бесзопасное расстояние - и только позиции соответсвующие
            # этому расстоянию могут быть использлованы для трансфера

            # 4.2.2. Рэк из нашей системы
            else:
                # 4.2.2.1. Заставляем робота остановиться
                self.unloader_robot.set_number_register(UNLOADER_NR_NUMBERS.move_status, UNLOADER_NR_VALUES.move_stop)
                safe_empty_position = None
                self.logger.info(f"Осущестлвяется поиск свободного места для трансфера...")
                # 4.2.2.2. Ждем момента появления доступного места для трансфера
                while not safe_empty_position:
                    last_occupied_rack_in_loader_zone = self.rack_manager.find_first_occupied_by_loader_rack_in_loader_zone()
                    if not last_occupied_rack_in_loader_zone:
                        last_occupied_rack_in_loader_zone = 0
                    danger_position_border = int(last_occupied_rack_in_loader_zone) + RACK_SAFE_DISTANCE
                    safe_empty_position = self.rack_manager.find_safe_empty_position_for_unloading(danger_position_border, self.logger)
                    self.logger.info(f"Граница опсаной зоны заканчивается на {danger_position_border} позиции!")
                    time.sleep(0.3)
                # 4.2.2.3. Определяем безопасную точку назначения для робота и отправляем туда робота
                self.logger.info(f"Найдено свободное место для трансфера!")
                self.unloader_robot.set_number_register(UNLOADER_NR_NUMBERS.stack_rack, safe_empty_position)
                self.rack_manager.occupy_racks_by_robot(
                    position=safe_empty_position,
                    busyness=RackOccupancy.BUSY_UNLOADER,
                    release=False, 
                    logger=self.logger
                )
                occupied_position = safe_empty_position 
                self.unloader_robot.set_number_register(UNLOADER_NR_NUMBERS.move_status, UNLOADER_NR_VALUES.move_start)
                self.rack_manager.get_rack_from_mindray_by_barcode(barcode, safe_empty_position)
                self.logger.info(f" Известный рэк успешно найден и извлекается!")

        
            # 4.3. Ждем инофрмации о завершении итерации роботом
            self.logger.info(f"Ожидание команды на завершение итерации...")
            self.wait_until(
                lambda: self.unloader_robot.get_number_register(
                    UNLOADER_NR_NUMBERS.iteration_starter
                )
                == UNLOADER_NR_VALUES.end,
                timeout=10.0,
                reason="Ожидание iteration_starter == end"
            )
            self.logger.info(f"Команда на завершение итерации получена!")

            # 4.4. Визуализируем конечное состояние системы
            self.logger.info(self.rack_manager.get_system_status())

        finally:
            # 4.5. Всегда освобождаем рэки.
            if occupied_position is not None:
                self.rack_manager.occupy_racks_by_robot(
                    position=occupied_position,
                    busyness=RackOccupancy.BUSY_UNLOADER,
                    release=True,
                    logger=self.logger
                )


    def _iteration_replacement(self) -> None:
        """
        Выполняет логику итерации переноса пустого рэка
        из зоны выгрузки в зону загрузки.
        """ 
        # 5.0 Объявляем итерацию
        self.logger.info("\n ====REPLACEMENT ITERATION====\n")
        self.unloader_robot.set_string_register(UNLOADER_SR_NUMBERS.iteration_type, UNLOADER_ITERATION_NAMES.replacement)

        # 5.1. Определяем точек назначения
        empty_rack_position = self.rack_manager.find_empty_rack_in_unloader_zone()
        empty_loader_position = self.rack_manager.find_empty_position_in_loader_zone()
        data_str = (                                                                      # Формируем пакет данных в виде строки роботу
            f"{int(empty_rack_position):02d} "
            f"{int(empty_loader_position):02d} "
        )
        self.unloader_robot.set_string_register(UNLOADER_SR_NUMBERS.unloader_data, data_str) 

        # 5.2. Стартуем итерацию после отправки всех данных роботу
        self.unloader_robot.set_number_register(UNLOADER_NR_NUMBERS.iteration_starter, UNLOADER_NR_VALUES.start)
        self.logger.info(f"[{threading.current_thread().name}] Отдана команда на исполнение итерации {UNLOADER_ITERATION_NAMES.replacement}!")

        # 5.3. Блокируем движения загрузкичку
        self.rack_manager.block_movement()

        try:
            # 5.4 Ждем перестановки пустого рэка из зоны выгрузки в зону загрузки
            self.logger.info(f"Ожидание перестановки пустого рэка из зоны выгрузки в зну загрузки...")
            self.wait_until(
                lambda: self.unloader_robot.get_number_register(
                    UNLOADER_NR_NUMBERS.grip_status
                )
                == UNLOADER_NR_VALUES.grip_bad,
                timeout=10.0,
                reason="Ожидание grip_status == grip_bad"
            )
            self.logger.info(f"Рэк успешно перемещен из зоны выгрузки в зону загрузки!")
            self.rack_manager.transfer_rack_from_unloader_to_loader(empty_loader_position, empty_rack_position, self.logger)

            # 5.5. Ждем инофрмации о завершении итерации роботом
            self.logger.info(f"Ожидание команды на завершение итерации...")
            self.wait_until(
                lambda: self.unloader_robot.get_number_register(
                    UNLOADER_NR_NUMBERS.iteration_starter
                )
                == UNLOADER_NR_VALUES.end,
                timeout=10.0,
                reason="Ожидание iteration_starter == end"
            )
            self.logger.info(f"Команда на завершение итерации получена!")

            # 5.6. Визуализируем конечное состояние системы
            self.logger.info(self.rack_manager.get_system_status())

        finally:
            # 5.7. Разблокируем движения загрузчику
            self.rack_manager.allow_movement()


    def run(self) -> None:
        self.logger.info("[Unloader] Поток запущен")

        # 0.1 Подготовка контекста
        ctx = IterationContext(
            robot=self.unloader_robot,
            starter_nr=UNLOADER_NR_NUMBERS.iteration_starter,
            starter_reset=UNLOADER_NR_VALUES.reset,
        )

        # 0.2 Подготовка робота
        self.prepare_robot(
            robot=self.unloader_robot, 
            program_name=self.cfg.robot_program_name
        )

        try:
            while not self.stop_event.is_set():
                # 1. Определяем основные параемтры для определения типа итерации
                rack_number: str | None = None                                                          # Опредеям переменные чтобы избежать UnboundLocalError 

                unloader_available_tripod = self.unloader_tripods_thread.get_available_tripod_name()    # Нахождение доступного трипода
                empty_loader_position = self.rack_manager.find_empty_position_in_loader_zone()          # Определяем пустое метсо зоне загрузки
                unloading_rack_info = self.rack_manager.check_non_empty_rack_in_unloader_zone()         # Проверяем наличие рэка, который можно разгружать
                empty_rack_in_unloader_zone = self.rack_manager.find_empty_rack_in_unloader_zone()

                rack_out = self._sensor("mindray_rack_out_present")                                     # Проверяем, не выехал ли рэк из миндрея
                table_in = self._sensor("unloader_table_present")                                       # Проверяем, задвинут ли столик
                emergency_rack_out = self._sensor("emergency_rack_present")                             # Проверяем, не уставнолвен ли экстренный рэка
                self._set_tower_missing(present=table_in, missing_flag="unloader_table_missing")        # Устанавливаем башню по статусу столика
                self._set_tower_flag_value(value=emergency_rack_out, flag="emergency_rack_out")         # Устанавливаем башню по наличию экстренного рэка
                
                #TODO а почему срабатывает rack_manager.find_empty_position_in_unloader_zone
                # 2. Определяем тип итерации
                if rack_out:
                    current_iteration_type = UNLOADER_ITERATION_NAMES.transfer
                elif empty_loader_position and empty_rack_in_unloader_zone:
                    current_iteration_type = UNLOADER_ITERATION_NAMES.replacement
                elif unloader_available_tripod and unloading_rack_info and table_in:
                    rack_number = unloading_rack_info
                    current_iteration_type = UNLOADER_ITERATION_NAMES.unloading
                else:
                    current_iteration_type = UNLOADER_ITERATION_NAMES.none

                # 3. Логика итерации опустошения рэков
                if current_iteration_type == UNLOADER_ITERATION_NAMES.unloading:
                    if rack_number is None:
                        self.logger.error("unloading выбран, но rack_number не определён")
                        continue
                    status, _ = self._execute_with_guard(
                        name=UNLOADER_ITERATION_NAMES.unloading,
                        ctx=ctx,
                        fn=lambda: self._iteration_unloading(
                            unloader_available_tripod=unloader_available_tripod,
                            rack_number=rack_number
                        )
                    )
                    if status == GuardResult.STOP: 
                        return
                    if status == GuardResult.SKIP: 
                        continue

                # 4. Логика итерации выгрузки рэка из миндрея
                if current_iteration_type == UNLOADER_ITERATION_NAMES.transfer:
                    status, _ = self._execute_with_guard(
                        name=UNLOADER_ITERATION_NAMES.transfer,
                        ctx=ctx,
                        fn=lambda: self._iteration_transfer()
                    )
                    if status == GuardResult.STOP: 
                        return
                    if status == GuardResult.SKIP: 
                        continue

                # 5. Логика итерации выгрузки рэка из миндрея\
                if current_iteration_type == UNLOADER_ITERATION_NAMES.replacement:
                    status, _ = self._execute_with_guard(
                        name=UNLOADER_ITERATION_NAMES.replacement,
                        ctx=ctx,
                        fn=lambda: self._iteration_replacement()
                    )
                    if status == GuardResult.STOP: 
                        return
                    if status == GuardResult.SKIP: 
                        continue

                #Время между иетрациями основного цикла
                time.sleep(0.1)

        except Exception as e:
            self.tower_state_store.update(critical_alarm=True)
            self.logger.fatal(f"Ошибка: {e}")
