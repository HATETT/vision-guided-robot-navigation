# src/vision_guided_robot_navigation/orchestration/runtime/robots/unloader_thread.py
import time
import logging
import threading

from src.vision_guided_robot_navigation.orchestration.runtime.robots.base_robot_thread import (
    BaseRobotThread, 
    IterationContext, 
    GuardResult
)
from src.vision_guided_robot_navigation.devices import CellRobot
from src.vision_guided_robot_navigation.config.unloader.config import UnloaderConfig
from src.vision_guided_robot_navigation.orchestration.runtime.tripods import TripodAvailabilityProvider
from src.vision_guided_robot_navigation.infrastructure.vision_client import VisionClient
from src.vision_guided_robot_navigation.orchestration.runtime.robots.protocol import (
    UNLOADER_NR_NUMBERS,
    UNLOADER_NR_VALUES,
    UNLOADER_SR_NUMBERS,
    UNLOADER_PR_NUMBERS,
    UNLOADER_ITERATION_NAMES,
)
from src.vision_guided_robot_navigation.domain import (
    LoadingTripod, 
)


class UnloaderRobotThread(BaseRobotThread):
    """
    Поток, выполняющий основную логику робота-выгрузчика.

    Остановка: через stop_event (threading.Event).
    Пока stop_event не выставлен, поток крутит свой цикл.
    """

    def __init__(
        self,
        unloader_robot: CellRobot,
        unloader_cfg: UnloaderConfig,
        unloader_tripods: dict[str, LoadingTripod],   # в эти штативы пробирки ставятся
        unloader_tripods_thread: TripodAvailabilityProvider,
        logger: logging.Logger,
        stop_event: threading.Event,
    ) -> None:
        super().__init__(name="UnloaderRobotThread", daemon=True, stop_event=stop_event, logger=logger)
        self.unloader_robot = unloader_robot
        self.unloader_tripods = unloader_tripods
        self.unloader_tripods_thread = unloader_tripods_thread
        self.cfg = unloader_cfg
        self.vision = VisionClient(base_url="http://127.0.0.1:8010", timeout_s=2.0)


        self.unloader_robot.set_pose_register(
            pr_id=9,
            x_val=0,
            y_val=0,
            z_val=0,
            a_val=0,
            b_val=0,
            c_val=0,
        )

    def _iteration_unload(self, *, unloader_available_tripod: str | None, tube_coordinates: dict[str, float]) -> None:
        """
        Выполняет логику итерации выгрузки пробирок из
        свала в штативы (триподы) выгрузки.
        
        :param unloader_available_tripod: Доступный трипод для загрузки в него пробирки
        :type unloader_available_tripod: str | None
        :param tube_coordinates: Словарь координат найденной в свале пробирки
        :type tube_coordinates: dict[str, float]

        example: tube_coordinates = {
            "x": 4,
            "y": 12,
            "z": 34,
            "a": 1.4,
            "b": 51.9,
            "c": 0
        }
        """

        # 3.1. Назначаем роботу тип итерации
        self.logger.info("\n ====UNLOAD ITERATION====\n")
        self.unloader_robot.set_string_register(UNLOADER_SR_NUMBERS.iteration_type, UNLOADER_ITERATION_NAMES.unloading)

        # 3.2 Записываем роботу координаты пробирки в свале
        self.unloader_robot.set_pose_register(
            pr_id=UNLOADER_PR_NUMBERS.tube_dump,
            x_val=tube_coordinates["x"],
            y_val=tube_coordinates["y"],
            z_val=tube_coordinates["z"],
            a_val=tube_coordinates["a"],
            b_val=tube_coordinates["b"],
            c_val=tube_coordinates["c"],
        )

        data_str = (
            f"{tube_coordinates['x']:08.3f} "
            f"{tube_coordinates['y']:08.3f} "
            f"{tube_coordinates['z']:08.3f} "
            f"{tube_coordinates['a']:08.3f} "
            f"{tube_coordinates['b']:08.3f} "
            f"{tube_coordinates['c']:08.3f}"
        )

        # 3.3. Определяем оставшиеся точки назначения робота
        print(unloader_available_tripod)
        tripod_number = int(unloader_available_tripod)
        tripod_place_number = self.unloader_tripods[unloader_available_tripod].get_tubes()
        data_str = (                                                                            # Формируем пакет данных в виде строки роботу
            f"{tripod_number:02d} "
            f"{tripod_place_number:02d} "
            f"{tube_coordinates['x']:07.3f} "
            f"{tube_coordinates['y']:07.3f} "
            f"{tube_coordinates['z']:07.3f} "
            f"{tube_coordinates['a']:07.3f} "
            f"{tube_coordinates['b']:07.3f} "
            f"{tube_coordinates['c']:07.3f}"
        )
        self.unloader_robot.set_string_register(UNLOADER_SR_NUMBERS.unloader_data, data_str)     # Отправляем роботу строку с данными

        try:
            # 3.4. Стартуем итерацию после отправки всех данных роботу
            self.unloader_robot.set_number_register(UNLOADER_NR_NUMBERS.iteration_starter, UNLOADER_NR_VALUES.start)
            self.logger.info(f"Отдана команда на исполнение итерации {UNLOADER_ITERATION_NAMES.unloading}!") 

            # 3.5. Ждем пока робот физически уберет пробирку из рэка
            # while not self.unloader_robot.get_number_register(UNLOADER_NR_NUMBERS.grip_status) == UNLOADER_NR_VALUES.grip_good:
            #     self.logger.info(f"Ожидание извлечения пробирки из свала...") 
            #     time.sleep(0.5)


            self.logger.info(f"Ожидание извлечения пробирки из свала...") 
            self.wait_until(
                lambda: self.unloader_robot.get_number_register(
                    UNLOADER_NR_NUMBERS.grip_status
                ) == UNLOADER_NR_VALUES.grip_good,
                timeout=600.0,
                reason="Ожидание grip_status == grip_good"
            )

            # 3.6. Ждем пока робот физически поставит пробирку в трипод
            self.logger.info(f"Ожидание установки пробирки в штатив...")
            self.wait_until(
                lambda: self.unloader_robot.get_number_register(
                    UNLOADER_NR_NUMBERS.grip_status
                )
                == UNLOADER_NR_VALUES.grip_bad,
                timeout=600.0,
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
                timeout=600.0,
                reason="Ожидание iteration_starter == end"
            )
            self.logger.info(f"Команда на завершение итерации получена!")

        finally:
            # 3.8. Логируем состояние штатива по окночанию итерации
            self.logger.info("Итерация UNLOAD завершена! Статус загружаемых штативов:")
            self.logger.info(self.unloader_tripods[unloader_available_tripod])



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
                unloader_available_tripod = self.unloader_tripods_thread.get_available_tripod_name()    # Нахождение доступного трипода
                # TEST: берём тестовый кадр с диска (положи файл в repo/test_data/frame.jpg)
                result = self.vision.predict_from_file("test_data/frame.jpg")
                tube_coordinates = result.as_dict() if result else None

                if tube_coordinates:
                    current_iteration_type = UNLOADER_ITERATION_NAMES.unloading
                else:
                    current_iteration_type = UNLOADER_ITERATION_NAMES.none

                # 3. Логика итерации опустошения свала пробирок
                if current_iteration_type == UNLOADER_ITERATION_NAMES.unloading:
                    status, _ = self._execute_with_guard(
                        name=UNLOADER_ITERATION_NAMES.unloading,
                        ctx=ctx,
                        fn=lambda: self._iteration_unload(
                            unloader_available_tripod=unloader_available_tripod,
                            tube_coordinates=tube_coordinates
                        )
                    )
                    if status == GuardResult.STOP: 
                        return
                    if status == GuardResult.SKIP: 
                        continue

                #Время между иетрациями основного цикла
                time.sleep(0.1)

        except Exception as e:
            self.logger.fatal(f"Ошибка: {e}")
