# src/mindray_automation_2/orchestration/runtime/robots/loader_thread.py
import time
import threading
import logging

from src.mindray_automation_2.orchestration.runtime.robots.base_robot_thread import BaseRobotThread, IterationContext, GuardResult
from src.mindray_automation_2.devices import CellRobot, Scanner
from src.mindray_automation_2.config.loader.config import LoaderConfig
from src.mindray_automation_2.orchestration.runtime.tripods import TripodAvailabilityProvider
from src.mindray_automation_2.tower import TowerStateStore
from src.mindray_automation_2.orchestration.runtime.robots.protocol import (
    LOADER_NR_NUMBERS,
    LOADER_NR_VALUES,
    LOADER_SR_NUMBERS,
    LOADER_ITERATION_NAMES,
)

from src.mindray_automation_2.domain import (
    RackManager, 
    Tripod, 
    LoadingTripod, 
    UnloadingTripod, 
    RackOccupancy,
)

class LoaderRobotThread(BaseRobotThread):
    """
    Поток, выполняющий основную логику робота-загрузчика.

    Остановка: через stop_event (threading.Event).
    Пока stop_event не выставлен, поток крутит свой цикл.
    """

    def __init__(
        self,
        rack_manager: RackManager,
        loader_robot: CellRobot,
        loader_scanner: Scanner,
        loader_cfg: LoaderConfig,
        loader_tripods: dict[str, UnloadingTripod],   # из этих штативов пробирки забираются
        unloader_tripods: dict[str, LoadingTripod],   # в эти штативы пробирки ставятся
        tower_state_store: TowerStateStore,
        loader_tripods_thread: TripodAvailabilityProvider, 
        logger: logging.Logger,
        stop_event: threading.Event,
    ) -> None:
        super().__init__(name="LoaderRobotThread", daemon=True, stop_event=stop_event, logger=logger)
        self.rack_manager = rack_manager
        self.loader_robot = loader_robot
        self.loader_scanner = loader_scanner
        self.loader_tripods = loader_tripods
        self.unloader_tripods = unloader_tripods
        self.tower_state_store = tower_state_store
        self.loader_tripods_thread = loader_tripods_thread
        self.cfg = loader_cfg
        self.scanner_cfg = loader_cfg.scanner

    def _iteration_loading(self, *, loader_available_tripod: str) -> None:
        """
        Выполняет логику итерации загрузки пробирок
        из штатива (трипода) в рэк с ориентацией штрих-кода.
        
        :param loader_available_tripod: Доступный трипод для взятия из него пробирки
        :type loader_available_tripod: str
        """

        if not loader_available_tripod:
            self.loader_robot.set_string_register(LOADER_SR_NUMBERS.iteration_type, LOADER_ITERATION_NAMES.none)
            self.logger.warning("Штатив был убран во время работы установки")
            return

        # 3.1. В цикле разбираем пробикри до заполнения рэка
        for _ in range(self.loader_tripods[loader_available_tripod].get_tubes()):
            self.logger.info("\n ====LOAD ITERATION====\n")
            self.loader_robot.set_string_register(LOADER_SR_NUMBERS.iteration_type, LOADER_ITERATION_NAMES.loading)  
            self.tower_state_store.update(loader_busy=True, loader_idle=False)  # Включаем огонь занятости робота-загрузкчика на сиганльной башни

            # 3.2. Проверяем появился ли заполенный рэк и можно ли его ставить в миндрей
            tubes_in_mindray = self.rack_manager.get_total_tubes_in_mindray()                        # Подсчет пробирок в миндрее
            tubes_in_unloader_rack_zone = self.rack_manager.get_total_tubes_in_unloader_zone()       # Подсчет пробирок в рэках для выгрузки
            available_places_in_unloader_tripods = sum(                                              # Подсчет пробирок штативах для выгрузки
                tripod.get_empty_places() 
                for tripod in self.unloader_tripods.values() 
                if tripod.availability
            )
            full_rack_info = self.rack_manager.check_full_rack_in_loader_zone()
            if full_rack_info and not (tubes_in_mindray >= available_places_in_unloader_tripods - tubes_in_unloader_rack_zone):
                self.loader_robot.set_string_register(LOADER_SR_NUMBERS.iteration_type, LOADER_ITERATION_NAMES.none)
                break

            # 3.3. Определяем точки назначения робота
            try: 
                tripod_tube_number = self.loader_tripods[loader_available_tripod].grab_tube()         # Номер пробирки в штативе
            except Exception as e:
                self.logger.warning("Штатив был убран во время работы установки")
                continue
            rack_info = self.rack_manager.get_nearest_available_rack_in_loader_zone()                 # Номер ближайшего доступного пустого рэка
            rack_number: str | None = None
            partially_full_rack_info = self.rack_manager.get_partially_filled_rack_in_loader_zone()   # Номер ближайшего доступного неполного рэка


            if rack_info:
                rack_number = partially_full_rack_info or rack_info                                   # Определяем рэк назначения                                 
            else:
                self.loader_robot.set_string_register(LOADER_SR_NUMBERS.iteration_type, LOADER_ITERATION_NAMES.none)
                break

            self.rack_manager.occupy_racks_by_robot(                                                  # Окуупируем ближайшие рэки 
                position=rack_number,  
                busyness=RackOccupancy.BUSY_LOADER, 
                release=False,
                logger=self.logger
            )

            try:
                rack_place_number = self.rack_manager.get_rack_tube_count(rack_number)                # Номер пустого гнезда в рэке
                data_str = (                                                                          # Формируем пакет данных в виде строки роботу
                    f"{int(loader_available_tripod):02d} "
                    f"{tripod_tube_number:02d} "
                    f"{int(rack_number):02d} "
                    f"{rack_place_number:02d}"
                )
                self.loader_robot.set_string_register(LOADER_SR_NUMBERS.loader_data, data_str) 

                # 3.4. Стартуем итерацию после отправки всех данных роботу
                self.loader_robot.set_number_register(LOADER_NR_NUMBERS.iteration_starter, LOADER_NR_VALUES.start) 
                self.logger.info(f"Отдана команда на исполнение итерации {LOADER_ITERATION_NAMES.loading}!") 

                # 3.5. Ждем ответа от робота - есть ли пробирка в штатвие?
                self.wait_until(
                    lambda: self.loader_robot.get_number_register(
                        LOADER_NR_NUMBERS.grip_status
                    )
                    != LOADER_NR_VALUES.grip_reset,
                    timeout=10.0,
                    reason="Ожидание grip_status == grip_reset"
                )

                # 3.5.1. Если пробирка есть
                if self.loader_robot.get_number_register(LOADER_NR_NUMBERS.grip_status) == LOADER_NR_VALUES.grip_good:
                    pass                                                                                            # Просто идем дальше             
                # 3.5.2. Если пробирки нет
                elif self.loader_robot.get_number_register(LOADER_NR_NUMBERS.grip_status) == LOADER_NR_VALUES.grip_bad:
                    self.logger.warning(f"В штативе нет пробирок! ---> Производится обнуление...")                     
                    self.loader_tripods[loader_available_tripod].set_availability(False)
                    self.loader_tripods[loader_available_tripod].set_tubes(Tripod.MIN_TUBES)
                    self.logger.warning("Штатив обнулен!")
                    self.loader_robot.set_string_register(LOADER_SR_NUMBERS.iteration_type, LOADER_ITERATION_NAMES.none)
                    self.logger.warning("Итерация прервана!")
                    break
                # 3.5.3 Сбрасываем для следующей итерации
                self.loader_robot.set_number_register(LOADER_NR_NUMBERS.grip_status, LOADER_NR_VALUES.grip_reset)        # Сбрасываем для следующей итерации

                # 3.6 Сканируем и ориентрируем пробикру
                self.logger.info(f"Ожидание команды сканирвоания...")
                self.wait_until(
                    lambda: self.loader_robot.get_number_register(
                    LOADER_NR_NUMBERS.scan_status 
                    )
                    != LOADER_NR_VALUES.scan_reset,
                    timeout=10.0,
                    reason="Ожидание scan_status == scan_reset"
                )
                self.logger.info(f"Команда на сканирование получена!")
                barcode, delay = self.loader_scanner.scan(timeout=self.scanner_cfg.timeout)
                # 3.6.1. Если смогли считать штриход - ставим пробирку в рэк
                if barcode != "NoRead":
                    self.loader_robot.set_number_register(LOADER_NR_NUMBERS.scan_delay, delay)
                    self.loader_robot.set_number_register(LOADER_NR_NUMBERS.scan_status, LOADER_NR_VALUES.scan_good)
                    self.rack_manager.add_tube_to_rack(rack_number, barcode)
                # 3.6.2. Если НЕ смогли считать штриход - возваращаем пробирку обртано в штатив на то же место
                else:
                    self.loader_robot.set_number_register(LOADER_NR_NUMBERS.scan_status, LOADER_NR_VALUES.scan_bad)
                # 3.6.3. Сбрасываем для следующей итерации
                self.loader_robot.set_number_register(LOADER_NR_NUMBERS.scan_status, LOADER_NR_VALUES.scan_reset)
                time.sleep(0.2)
                self.loader_robot.set_number_register(LOADER_NR_NUMBERS.scan_delay, LOADER_NR_VALUES.delay_reset)
                
                # 3.7. Ждем инофрмации о завершении итерации роботом
                self.logger.info(f"Ожидание команды на завершение итерации...")
                self.wait_until(
                    lambda: self.loader_robot.get_number_register(
                        LOADER_NR_NUMBERS.iteration_starter
                    )
                    == LOADER_NR_VALUES.end,
                    timeout=10.0,
                    reason="Ожидание iteration_starter == end"
                )
                self.logger.info(f"Команда на завершение итерации получена!")

                # 3.8. Логируем состояние рэка и штатива по окночанию итерации
                self.rack_manager.log_rack_info(rack_number, self.logger)
                self.logger.info(self.loader_tripods[loader_available_tripod])
            
            finally:
                # 3.9. Возваращем стутус "FREE" ранее оккупированным рэкам
                if rack_number is not None:
                    self.rack_manager.occupy_racks_by_robot(
                        position=rack_number,
                        busyness=RackOccupancy.BUSY_LOADER,
                        release=True,
                        logger=self.logger,
                    )  

    def _iteration_stacking(self, *, position: str, rack_to_mindray_amount: int) -> None:
        """
        Выполняет логику итерации постановки заполненного 
        пробирками рэка в миндрей и его отправки на обработку.
        
        :param position: Позиция не пустого рэка
        :param rack_to_mindray_amount: Количесвто рэков, котоыре нужно перенести в миндрей
        """ 
        # 4.0 Объявляем итерацию
        self.logger.info("\n ====STACK ITERATION====\n")
        self.loader_robot.set_string_register(LOADER_SR_NUMBERS.iteration_type, LOADER_ITERATION_NAMES.stacking)
        self.tower_state_store.update(loader_busy=True, loader_idle=False)  # Включаем огонь занятости робота-загрузкчика на сиганльной башни 
        
        # 4.1. Оккупируем ближайшие рэки
        self.rack_manager.occupy_racks_by_robot(
            position=position, 
            busyness=RackOccupancy.BUSY_LOADER, 
            release=False, 
            logger=self.logger
        )

        try:
            # 4.2. Определяем точки назанчения робота 
            data_str = (                                                                # Формируем пакет данных в виде строки роботу
                f"{int(rack_to_mindray_amount):02d} "                                   # Количесвто рэков на постановку                                                           
                f"{int(position):02d}"                                                  # Номер рэка 
            )
            self.loader_robot.set_string_register(LOADER_SR_NUMBERS.loader_data, data_str)  # Отправляем роботу строку с данными

            # 4.3. Стартуем итерацию после отправки всех данных роботу
            self.loader_robot.set_number_register(LOADER_NR_NUMBERS.iteration_starter, LOADER_NR_VALUES.start) 
            self.logger.info(f"Отдана команда на исполнение итерации {LOADER_ITERATION_NAMES.stacking}!")

            # 4.4. Обновляем рэк мэнэджер, убирая рэк в миндрей
            self.rack_manager.move_rack_to_mindray(position, self.logger)
            self.logger.info(f"Рэк {position} перемещен в MindRay")

            # 4.5. Делаем рэки доступными после ухода робота из зоны загрузки
            self.rack_manager.occupy_racks_by_robot(
                position=position, 
                busyness=RackOccupancy.BUSY_LOADER, 
                release=True, 
                logger=self.logger
            )

            # ====== ВАЖНО ======
            # Код робота должен нажимать на кнопку по при rack_to_mindray_amount = 1, иначе рэки никогда не будут загружены
            # TODO выяснить временной алгоритм блока загрузки миндрея

            # 4.6. Сбрасываем флаг и ждем готовности робота двигаться дальше
            self.loader_robot.set_number_register(LOADER_NR_NUMBERS.move_status, LOADER_NR_VALUES.move_stop)
            self.wait_until(
                lambda: self.rack_manager.is_movement_allowed() 
                == True,
                timeout=10.0,
                reason="Ожидание is_movement_allowed == True"
            )
            self.loader_robot.set_number_register(LOADER_NR_NUMBERS.move_status, LOADER_NR_VALUES.move_start)

            # 4.7. Ждем инофрмации о завершении итерации роботом
            self.logger.info(f"Ожидание команды на завершение итерации...")
            self.wait_until(
                lambda: self.loader_robot.get_number_register(
                    LOADER_NR_NUMBERS.iteration_starter
                )
                == LOADER_NR_VALUES.end,
                timeout=10.0,
                reason="Ожидание iteration_starter == end"
            )
            self.logger.info(f"Команда на завершение итерации получена!")

            # 4.8. Логируем состояние всех рэков после постановки рэка в миндрей
            self.logger.info(self.rack_manager.get_system_status())

        finally:
            # 4.9. Всегда освобождаем рэки в конце
            self.rack_manager.occupy_racks_by_robot(
                position=position, 
                busyness=RackOccupancy.BUSY_LOADER, 
                release=False, 
                logger=self.logger
            )

    def run(self) -> None:
        self.logger.info("[Loader] Поток запущен")
        
        try:
            # 0.1 Подготовка контекста
            ctx = IterationContext(
                robot=self.loader_robot,
                starter_nr=LOADER_NR_NUMBERS.iteration_starter,
                starter_reset=LOADER_NR_VALUES.reset,
            )

            # 0.2 Подготовка робота
            self.prepare_robot(
                robot=self.loader_robot, 
                program_name=self.cfg.robot_program_name
            )

            while not self.stop_event.is_set():
                # 1. Определяем основные параемтры для определения типа итерации
                position: str | None = None                                                              # Опредеям переменные чтобы избежать UnboundLocalError   
                rack_to_mindray_amount: int | None = None                                                # Опредеям переменные чтобы избежать UnboundLocalError 
                  
                loader_available_tripod = self.loader_tripods_thread.get_available_tripod_name()         # Нахождение доступного трипода
                full_rack_info = self.rack_manager.check_full_rack_in_loader_zone()                      # Проверка наличия полных рэков 
                partially_full_rack_info = self.rack_manager.get_partially_filled_rack_in_loader_zone()  # Проверка наличия частично заполненного рэка
                tubes_in_mindray = self.rack_manager.get_total_tubes_in_mindray()                        # Подсчет пробирок в миндрее
                tubes_in_unloader_rack_zone = self.rack_manager.get_total_tubes_in_unloader_zone()       # Подсчет пробирок в рэках для выгрузки
                available_racks_in_loader_zone = self.rack_manager.has_available_racks_in_loader_zone()  # Наличие доступного рэка для загрузки в него пробирок
                available_places_in_unloader_tripods = sum(                                              # Подсчет пробирок штативах для выгрузки
                    tripod.get_empty_places() 
                    for tripod in self.unloader_tripods.values() 
                    if tripod.availability
                )
                not_enough_space_in_unloader_zone = tubes_in_mindray >= available_places_in_unloader_tripods - tubes_in_unloader_rack_zone

                # 2. Определяем тип итерации на основании теперь известных параметров
                if full_rack_info and not not_enough_space_in_unloader_zone:
                    position, rack_to_mindray_amount = full_rack_info
                    current_iteration_type = LOADER_ITERATION_NAMES.stacking
                elif not loader_available_tripod and partially_full_rack_info and not not_enough_space_in_unloader_zone:
                    position = partially_full_rack_info
                    rack_to_mindray_amount = 5
                    current_iteration_type = LOADER_ITERATION_NAMES.stacking
                elif loader_available_tripod and available_racks_in_loader_zone:
                    current_iteration_type = LOADER_ITERATION_NAMES.loading
                else:
                    current_iteration_type = LOADER_ITERATION_NAMES.none
                    self.tower_state_store.update(loader_busy=False, loader_idle=True)  # Включаем огонь свободы робота-загрузкчика на сиганльной башни                        

                # 3. Логика итерации загрузки пробирок в рэки
                if current_iteration_type == LOADER_ITERATION_NAMES.loading:
                    status, _ = self._execute_with_guard(
                        name=LOADER_ITERATION_NAMES.loading,
                        ctx=ctx,
                        fn=lambda: self._iteration_loading(
                            loader_available_tripod=loader_available_tripod, 
                        )
                    )
                    if status == GuardResult.STOP: 
                        return
                    if status == GuardResult.SKIP: 
                        continue

                # 4. Логика итерации загрузки рэков м миндрей
                if current_iteration_type == LOADER_ITERATION_NAMES.stacking:
                    if position is None or rack_to_mindray_amount is None:
                        self.logger.error("stacking выбран, но position/rack_to_mindray_amount не заданы")
                        continue
                    status, _ = self._execute_with_guard(
                        name=LOADER_ITERATION_NAMES.stacking,
                        ctx=ctx,
                        fn=lambda: self._iteration_stacking(
                            position=position, 
                            rack_to_mindray_amount=rack_to_mindray_amount,
                        )
                    )
                    if status == GuardResult.STOP: 
                        return
                    if status == GuardResult.SKIP: 
                        continue

                #Время между иетрациями основного цикла-*
                time.sleep(0.1)

        except Exception as e:
            self.tower_state_store.update(critical_alarm=True)
            self.logger.fatal(f"Ошибка: {e}")
