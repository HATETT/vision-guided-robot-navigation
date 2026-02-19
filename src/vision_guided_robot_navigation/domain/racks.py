# src/vision_guided_robot_navigation/domain/racks.py
from enum import Enum
from typing import Dict, Optional, Tuple, List
import random
import threading
import logging


RACK_SAFE_DISTANCE = 3


class RackStatus(Enum):
    """Статусы заполненности рэков"""
    EMPTY = "empty"         # Пустой
    PARTIAL = "partial"     # Частично заполнен
    FULL = "full"           # Полностью заполнен
    NOT_EXIST = "not_exist" # Не находится в рабочей области


class RackOccupancy(Enum):
    """Статусы занятости рэков"""
    FREE = "free"          # Свободен
    BUSY_LOADER = "busy_loader"  # Занят роботом 1
    BUSY_UNLOADER = "busy_unloader"  # Занят роботом 2


class Rack:
    MAX_TUBES = 10      # Максимальное количество пробирок в рэке
    
    def __init__(self, name: str, tube_count=0):
        self.name = name
        self._tube_count = 0
        self._occupancy = RackOccupancy.FREE 
        self._barcodes = []  # Массив для хранения штрихкодов
        self.set_tube_count(tube_count)
    

    # ----------------------ЗАНЯТОСТЬ----------------------
    def get_occupancy(self):
        return self._occupancy
    
    def set_occupancy(self, new_occupancy):
        if not isinstance(new_occupancy, RackOccupancy):
            raise ValueError("Статус занятости должен соответствовать RackOccupancy")
        self._occupancy = new_occupancy
    
    def occupy_by_loader(self):
        """Занять рэк загрузчиком"""
        self.set_occupancy(RackOccupancy.BUSY_LOADER)
    
    def occupy_by_unloader(self):
        """Занять рэк выгрузчиком"""
        self.set_occupancy(RackOccupancy.BUSY_UNLOADER)
    
    def release(self):
        """Освободить рэк"""
        self.set_occupancy(RackOccupancy.FREE)

    def is_busy(self):
        """Проверить, занят ли рэк"""
        return self._occupancy != RackOccupancy.FREE
    
    def is_available(self):
        """Доступен ли рэк для операций"""
        return self._occupancy == RackOccupancy.FREE
    

    # ----------------------ЗАПОЛНЕННОСТЬ----------------------
    def get_status(self):
        """Получить статус заполненности (вычисляется автоматически)"""
        if self._tube_count == 0:
            return RackStatus.EMPTY
        elif self._tube_count == self.MAX_TUBES:
            return RackStatus.FULL
        else:
            return RackStatus.PARTIAL
        

    # ----------------------ШТРИХКОДЫ----------------------
    def get_barcodes(self):
        return self._barcodes.copy()  # Возвращаем копию для безопасности
    
    def add_barcode(self, barcode: str):
        """Добавить штрихкод в массив"""
        self._barcodes.append(barcode)

    def has_barcode(self, barcode: str) -> bool:
        """Проверить наличие штрихкода в рэке"""
        return barcode in self._barcodes

    def get_first_barcode(self) -> Optional[str]:
        """Получить первый штрихкод из рэка (для идентификации)"""
        return self._barcodes[0] if self._barcodes else None

    def gen_barcode(self) -> str:
        """Генерация случайного штрихкода (заглушка для внешней функции)"""
        return f"BC_{random.randint(10000, 99999)}"

    
    # ----------------------ОПЕРАЦИИ С ПРОБИРКАМИ----------------------
    def get_tube_count(self):
        return self._tube_count
    
    def set_tube_count(self, count):
        if not 0 <= count <= self.MAX_TUBES:
            raise ValueError(f"Количество пробирок должно быть между 0 и {self.MAX_TUBES}")
        self._tube_count = count

    def add_tube(self, barcode: str = None):
        """Добавить пробирку со штрихкодом"""
        if self.get_tube_count() >= self.MAX_TUBES:
            raise ValueError(f"Рэк {self.name} заполнен!")
        
        # Если штрихкод не передан, генерируем его
        if barcode is None:
            barcode = "NoRead" #self.gen_barcode()
        
        self.add_barcode(barcode)
        self.set_tube_count(self.get_tube_count() + 1)
    
    def remove_tube(self):
        """Удалить пробирку (последнюю добавленную)"""
        if self.get_tube_count() <= 0:
            raise ValueError(f"Рэк {self.name} пуст!")
        
        # Удаляем последний штрихкод
        if self._barcodes:
            self._barcodes.pop()
        
        self.set_tube_count(self.get_tube_count() - 1)
    

    # ----------------------ВСПОМОГАТЕЛЬНЫЕ МЕТОДЫ----------------------
    def is_empty(self):
        return self.get_tube_count() == 0
    
    def is_full(self):
        return self.get_tube_count() == self.MAX_TUBES
    
    def can_add_tubes(self):
        return self.get_tube_count() < self.MAX_TUBES and self.is_available()
    
    def has_tubes(self):
        return self.get_tube_count() > 0
    
    def __str__(self):
        status = self.get_status()
        occupancy = self.get_occupancy()
        barcodes_count = len(self._barcodes)
        return f"Рэк {self.name} (Заполненность: {status.value}, Занятость: {occupancy.value}, Пробирки: {self._tube_count}/{self.MAX_TUBES}, Штрихкоды: {barcodes_count})"


class RackManager:
    """Менеджер для управления рэками в системе с разделением зон"""
    
    def __init__(self, racks_in_loading_zone: int, racks_in_unloading_zone: int):
        # Словарь: ключ - физическое место, значение - объект Rack или None
        self.racks: Dict[str, Optional[Rack]] = {}
        # Массив для рэков в MindRay (вместо очереди)
        self.mindray_racks: List[Rack] = []

        self.racks_in_loading_zone = racks_in_loading_zone
        self.racks_in_unloading_zone = racks_in_unloading_zone

        # Ивент для избежания коллизий роботов при перестановке рэков из зоны выгрузки в зону загрузки
        self._movement_block_event = threading.Event()
        
        # Лок на весь менеджер (re-entrant, т.к. методы зовут друг друга)
        self._lock = threading.RLock()

        # Зоны роботов
        self.loader_zone = [f"{rack+1}" for rack in range(self.racks_in_loading_zone)]  # ["1", "2", "3", "4", "5", "6"]      # Зона загрузчика
        self.unloader_zone = [f"{rack+racks_in_loading_zone+1}" for rack in range(self.racks_in_unloading_zone)]       #["7", "8", "9", "10", "11", "12", "13", "14", "15", "16"]  # Зона выгрузчика
        
        # Инициализация начальных позиций рэков
        self._initialize_racks()
    
    def _initialize_racks(self):
        """Инициализация начального состояния рэков"""
        all_positions = self.loader_zone + self.unloader_zone
        for pos in all_positions:
            self.racks[pos] = Rack(f"{pos}")
    
    # ---------------------- ОСНОВНЫЕ МЕТОДЫ ДЛЯ РОБОТОВ ----------------------
    def has_available_racks_in_loader_zone(self) -> bool:
        """
        Проверить, есть ли хотя бы один доступный рэк в зоне загрузки
        для добавления пробирок
        
        Returns:
            bool: True если есть хотя бы один доступный рэк, иначе False
        """
        with self._lock:
            for position in self.loader_zone:
                rack = self.racks[position]
                if rack and rack.is_available() and rack.can_add_tubes():
                    return True
            return False
    
    def get_available_racks_in_loader_zone(self) -> List[Tuple[str, Rack]]:
        """
        Получить список всех доступных рэков в зоне загрузки
        
        Returns:
            List[Tuple[str, Rack]]: Список кортежей (позиция, рэк)
        """
        with self._lock:
            available_racks = []
            for position in self.loader_zone:
                rack = self.racks[position]
                if rack and rack.is_available() and rack.can_add_tubes():
                    available_racks.append((position, rack))
            return available_racks
    

    def find_rack_position(self, target_rack: Rack) -> Optional[str]:
        """
        Найти позицию рэка в зоне загрузки или выгрузки
        
        Args:
            target_rack: Рэк для поиска
            
        Returns:
            str: Позиция рэка или None если рэк не найден
        """
        # Ищем во всех позициях системы
        with self._lock:
            for position, rack in self.racks.items():
                if rack and rack.name == target_rack.name:
                    return position
            
            return None

    # def get_first_available_rack_in_loader_zone(self) -> Optional[Tuple[str, Rack]]:
    #     """
    #     Найти первый доступный рэк в зоне загрузки
        
    #     Returns:
    #         Optional[Tuple[str, Rack]]: (позиция, рэк) или None если нет доступных
    #     """
    #     for position in self.loader_zone:
    #         rack = self.racks[position]
    #         if rack and rack.is_available() and rack.can_add_tubes():
    #             return position, rack
    #     return None
    
    def check_full_rack_in_loader_zone(self) -> Optional[Tuple[str, int]]:
        """
        Проверить наличие полного рэка в зоне загрузки для помещения в MindRay
        Возвращает (позиция, количество_полных_рэков) или None если нет полных рэков
        """
        with self._lock:
            full_racks = []
            for position in self.loader_zone:
                rack = self.racks[position]
                if rack and rack.is_full() and rack.is_available():
                    full_racks.append((position, rack))
            
            if full_racks:
                position, rack = full_racks[-1]
                return position, len(full_racks)
            return None
    
    def check_non_empty_rack_in_unloader_zone(self) -> Optional[str]:
        """
        Проверить наличие НЕ ПУСТОГО рэка в зоне выгрузки для работы с ним
        Возвращает (позиция, рэк) или None если нет не пустых рэков
        
        Не пустой рэк = рэк, который содержит хотя бы одну пробирку
        """
        with self._lock:
            for position in self.unloader_zone:
                rack = self.racks[position]
                if rack and not rack.is_empty() and rack.is_available():
                    return position
            return None
    
    def move_rack_to_mindray(self, position: str, logger: logging.Logger) -> bool:
        """
        Переместить рэк из зоны загрузки в MindRay (в массив)
        """
        with self._lock:
            if position not in self.loader_zone:
                logger.critical(f"Ошибка: позиция {position} не в зоне загрузки")
                return False
            
            rack = self.racks[position]
            if not rack:
                logger.critical(f"Ошибка: в позиции {position} нет рэка")
                return False
            
            # if not rack.is_full():
            #     self.logger.critical(f"Ошибка: рэк {rack.name} не заполнен полностью")
            #     return False
            
            if not rack.is_available():
                logger.critical(f"Ошибка: рэк {rack.name} занят")
                return False
            
            # Перемещаем рэк в MindRay (добавляем в массив)
            self.racks[position] = None
            self.mindray_racks.append(rack)
            
            logger.info(f"Рэк {rack.name} перемещен из позиции {position} в MindRay")
            logger.info(f"Штрихкоды рэка: {rack.get_barcodes()}")
            return True
    
    def find_rack_by_barcode(self, barcode: str) -> Optional[Rack]:
        """
        Найти рэк в MindRay по штрихкоду
        Возвращает рэк или None если не найден
        """
        with self._lock:
            for rack in self.mindray_racks:
                if rack.has_barcode(barcode):
                    return rack
            return None
    
    def get_rack_from_mindray_by_barcode(self, barcode: str, target_position: int, logger: logging.Logger) -> Optional[Tuple[Rack, str]]:
        """
        Извлечь рэк из MindRay по считанному штрихкоду
        Возвращает (рэк, позиция_для_размещения) или None если рэк не найден
        """
        # Находим рэк по штрихкоду
        with self._lock:
            rack = self.find_rack_by_barcode(barcode)
            if not rack:
                logger.warning(f"Рэк со штрихкодом {barcode} не найден в MindRay")
                return None
            
            # # Находим самую дальнюю свободную позицию в зоне выгрузки
            # target_position = self.find_farthest_empty_position_in_unloader_zone()
            # if not target_position:
            #     logger.warning("Нет свободных позиций в зоне выгрузки")
            #     return None
            
            # Удаляем рэк из массива MindRay и помещаем в зону выгрузки
            self.mindray_racks.remove(rack)
            self.racks[target_position] = rack
            rack.release()  # Освобождаем рэк
            
            logger.info(f"Рэк {rack.name} извлечен из MindRay по штрихкоду {barcode} и помещен в позицию {target_position}")
            return rack, target_position
    
    def get_total_tubes_in_mindray(self) -> int:
        """
        Рассчитать общее количество пробирок во всех рэках в MindRay
        
        Returns:
            int: Общее количество пробирок в MindRay
        """
        with self._lock:
            total_tubes = 0
            for rack in self.mindray_racks:
                total_tubes += rack.get_tube_count()
            return total_tubes
    
    def find_empty_rack_in_unloader_zone(self) -> Optional[str]:
        """
        Найти самый ближний пустой рэк в зоне выгрузки
        Возвращает позицию или None если нет пустых рэков
        """
        with self._lock:
            for position in reversed(self.unloader_zone):
                rack = self.racks[position]
                if rack and rack.is_empty() and rack.is_available():
                    return position
            return None
    
    def find_empty_position_in_loader_zone(self) -> Optional[str]:
        """
        Найти пустую позицию в зоне загрузки
        Возвращает позицию или None если нет пустых позиций
        """
        with self._lock:
            for position in self.loader_zone:
                if self.racks[position] is None:
                    return position
            return None
    

    def find_empty_position_in_unloader_zone(self) -> Optional[List[str]]:
        """
        Найти пустую позицию в зоне выгрузки
        Возвращает позицию или None если нет пустых позиций
        """
        with self._lock:
            empty_positions = []
            for position in self.unloader_zone:
                if self.racks[position] is None:
                    empty_positions.append(position)
            return empty_positions if empty_positions else None
    

    def find_safe_empty_position_for_unloading(self, danger_border: int, logger: logging.Logger) -> Optional[str]:
        """
        Найти безопасную пустую позицию для выгрузки с учетом зоны безопасности
        
        Args:
            danger_border: Граница опасной зоны (позиция занятого рэка + SAFETY_RACK_DISTANCE)
        
        Returns:
            Optional[str]: Безопасная позиция или None если нет подходящих
        """
        with self._lock:
            empty_positions = self.find_empty_position_in_unloader_zone()
            logger.info(f"Свободные пустые места - {empty_positions}")
            if not empty_positions:
                return None
            
            # Ищем первую подходящую позицию 
            for empty_position in empty_positions:
                if int(empty_position) > danger_border:
                    return empty_position
            
            return None
    

    def transfer_rack_from_unloader_to_loader(self, empty_loader_position, empty_rack_position, logger: logging.Logger) -> Optional[Tuple[str, str]]:
        """
        Переместить самый дальний пустой рэк из зоны выгрузки в пустую позицию зоны загрузки
        Возвращает (откуда_переместили, куда_переместили) или None если перемещение невозможно
        """
        # empty_loader_position = self.find_empty_position_in_loader_zone()
        # if not empty_loader_position:
        #     pself.logger.critical("Нет пустых позиций в зоне загрузки")
        #     return None
        
        # empty_rack_position = self.find_empty_rack_in_unloader_zone()
        # if not empty_rack_position:
        #     self.logger.critical("Нет пустых рэков в зоне выгрузки")
        #     return None
        
        # Перемещаем рэк
        with self._lock:
            rack = self.racks[empty_rack_position]
            self.racks[empty_rack_position] = None
            self.racks[empty_loader_position] = rack
            
            logger.info(f"Рэк {rack.name} перемещен из {empty_rack_position} в {empty_loader_position}")
            return empty_rack_position, empty_loader_position
    

    def find_farthest_empty_position_in_unloader_zone(self) -> Optional[str]:
        """
        Найти самую дальнюю свободную позицию в зоне выгрузки
        """
        with self._lock:
            for position in reversed(self.unloader_zone):
                if self.racks[position] is None:
                    return position
            return None
    

    def get_nearest_available_rack_in_loader_zone(self) -> Optional[str]:
        """
        Найти БЛИЖАЙШИЙ доступный рэк в зоне загрузки
        Возвращает (позиция) или None если нет доступных
        
        Ближайший = с наименьшим номером позиции в loader_zone
        """
        with self._lock:
            for position in self.loader_zone:
                rack = self.racks[position]
                if rack and rack.is_available() and rack.can_add_tubes():
                    return position
            return None


    def get_partially_filled_rack_in_loader_zone(self) -> Optional[str]:
        """
        Найти БЛИЖАЙШИЙ частично заполненный рэк в зоне загрузки
        Возвращает (позиция) или None если нет частично заполненных рэков
        
        Частично заполненный = содержит от 1 до 9 пробирок (не пустой и не полный)
        """
        with self._lock:
            for position in self.loader_zone:
                rack = self.racks[position]
                if (rack and 
                    rack.is_available() and 
                    not rack.is_empty() and 
                    not rack.is_full()):
                    return position
            return None
    
    
    def get_total_tubes_in_unloader_zone(self) -> int:
        """
        Рассчитать общее количество пробирок во всех рэках в зоне выгрузки
        
        Returns:
            int: Общее количество пробирок в зоне выгрузки
        """
        with self._lock:
            total_tubes = 0
            for position in self.unloader_zone:
                rack = self.racks[position]
                if rack:
                    total_tubes += rack.get_tube_count()
            return total_tubes
    

    def get_total_tubes_in_loader_zone(self) -> int:
        """
        Рассчитать общее количество пробирок во всех рэках в зоне загрузки
        
        Returns:
            int: Общее количество пробирок в зоне загрузки
        """
        with self._lock:
            total_tubes = 0
            for position in self.loader_zone:
                rack = self.racks[position]
                if rack:
                    total_tubes += rack.get_tube_count()
            return total_tubes
    

    def occupy_racks_by_robot(self, position: str, busyness: RackOccupancy, release: bool, logger: logging.Logger): 
        """"Задает близлежащим рэкам статусы занятости во избежание столкнвоений роботов в процессе совместной работы"""
        with self._lock:
            if busyness == RackOccupancy.BUSY_LOADER:
                multiplicator = 1
            elif busyness == RackOccupancy.BUSY_UNLOADER:
                multiplicator = -1
            else:
                raise ValueError(f"Неподдерживаемый статус занятости: {busyness}")
            
            for i in range(RACK_SAFE_DISTANCE):
                new_state_position = str(int(position)+(i+1)*multiplicator)
                rack = self.get_rack(new_state_position)
                if rack:
                    if release:
                        rack.set_occupancy(RackOccupancy.FREE)
                        logger.info(f"Рэку в позиции {new_state_position} присвоен стаутс {RackOccupancy.FREE}")
                    else:
                        rack.set_occupancy(busyness)
                        logger.info(f"Рэку в позиции {new_state_position} присвоен стаутс {busyness}")
    

    def find_first_occupied_by_loader_rack_in_loader_zone(self) -> Optional[str]:
        """
        Найти ПЕРВЫЙ рэк в зоне загрузки, занятый роботом-загрузчиком (BUSY_ROBOT_1)
        Returns:
            Optional[str]: (позиция) или None если нет занятых роботом 1 рэков
        """
        with self._lock:
            for position in self.loader_zone:
                rack = self.racks[position]
                if (rack and 
                    rack.get_occupancy() == RackOccupancy.BUSY_LOADER):
                    return position
            return None


    # ---------------------- БЕЗОПАСНЫЕ МЕТОДЫ РАБОТЫ С РЭКАМИ ----------------------

    def get_rack_tube_count(self, position: str) -> int:
        """
        Потокобезопасное получение количесвта пробирок в рэке
        """
        with self._lock:
            rack = self.get_rack(position)
            if rack is None:
                raise RuntimeError(f"Нет рэка в позиции {position}")
            return rack.get_tube_count()
        
    def log_rack_info(self, position: str, logger: logging.Logger) -> str:
        """
        Потокобезопасное логирование рэка
        """
        with self._lock:
            rack = self.get_rack(position)
            if rack is None:
                raise RuntimeError(f"Нет рэка в позиции {position}")
            logger.info(rack)

    def add_tube_to_rack(self, position: str, barcode: str) -> None:
        """
        Потокобезопасное добавление пробирки в рэк
        """
        with self._lock:
            rack = self.get_rack(position)
            if rack is None:
                raise RuntimeError(f"Нет рэка в позиции {position}")
            rack.add_tube(barcode)
            # при желании можно логировать тут

    def remove_tube_from_rack(self, position: str) -> None:
        """
        Потокобезопасное добавление пробирки в рэк
        """
        with self._lock:
            rack = self.get_rack(position)
            if rack is None:
                raise RuntimeError(f"Нет рэка в позиции {position}")
            rack.remove_tube()

    def is_movement_allowed(self) -> bool:
        """
        Проверка возможности движения
        """
        return not self._movement_block_event.is_set()

    def block_movement(self) -> None:
        """
        Запрет на движжение
        """
        with self._lock:
            self._movement_block_event.set()

    def allow_movement(self) -> None:
        """
        Разрешение на движение
        """
        with self._lock:
            self._movement_block_event.clear()

    # ---------------------- ВСПОМОГАТЕЛЬНЫЕ МЕТОДЫ ----------------------
    
    def get_rack(self, position: str) -> Optional[Rack]:
        """Получить рэк по позиции"""
        with self._lock:
            return self.racks.get(position)
    
    def get_mindray_racks_count(self) -> int:
        """Получить количество рэков в MindRay"""
        with self._lock:
            return len(self.mindray_racks)
    
    def get_mindray_barcodes(self) -> List[str]:
        """Получить все штрихкоды из рэков в MindRay"""
        with self._lock:
            all_barcodes = []
            for rack in self.mindray_racks:
                all_barcodes.extend(rack.get_barcodes())
            return all_barcodes
    
    def get_loader_zone_status(self) -> List[Tuple[str, Optional[Rack]]]:
        """Получить статус зоны загрузки"""
        with self._lock:
            return [(pos, self.racks[pos]) for pos in self.loader_zone]
    
    def get_unloader_zone_status(self) -> List[Tuple[str, Optional[Rack]]]:
        """Получить статус зоны выгрузки"""
        with self._lock:
            return [(pos, self.racks[pos]) for pos in self.unloader_zone]
    
    def get_system_status(self):
        """Вернуть строку со статусом всей системы"""
        with self._lock:
            lines = []
            lines.append("\n" + "="*50)
            lines.append("СТАТУС СИСТЕМЫ")
            lines.append("="*50)
            
            lines.append(f"\nЗОНА ЗАГРУЗКИ (1-{self.racks_in_loading_zone}):")
            for position, rack in self.get_loader_zone_status():
                status = rack if rack else "[ПУСТО]"
                lines.append(f"  {position}: {status}")
            
            lines.append(f"\nЗОНА ВЫГРУЗКИ ({self.racks_in_unloading_zone}-{self.racks_in_unloading_zone+self.racks_in_loading_zone}):")
            for position, rack in self.get_unloader_zone_status():
                status = rack if rack else "[ПУСТО]"
                lines.append(f"  {position}: {status}")
            
            lines.append(f"\nРэков в MindRay: {self.get_mindray_racks_count()}")
            for i, rack in enumerate(self.mindray_racks):
                lines.append(f"  {i+1}. {rack.name} (штрихкоды: {len(rack.get_barcodes())})")
        
            return '\n'.join(lines)
        
    def build_short_racks_status(self) -> str:
        """
        Короткий статус: только имя рэка и пробирки X/Y.
        Плюс итоги по зонам и по MindRay.
        """
        with self._lock:
            lines: list[str] = []
            lines.append("\n" + "=" *50)
            lines.append("СТАТУС СИСТЕМЫ")
            lines.append("=" *50)

            # ===== ЗОНА ЗАГРУЗКИ =====
            lines.append(f"\nЗОНА ЗАГРУЗКИ (1-{self.racks_in_loading_zone}):")
            for position, rack in self.get_loader_zone_status():
                if rack is None:
                    lines.append(f"  {position}: [ПУСТО]")
                    continue
                lines.append(f"  {position}: Рэk {rack.name} — {rack.get_tube_count()}/{rack.MAX_TUBES}")

            try:
                total_loader = self.get_total_tubes_in_loader_zone()
            except Exception:
                total_loader = 0
            lines.append(f"Итого пробирок в зоне загрузки: {total_loader}")

            # ===== ЗОНА ВЫГРУЗКИ =====
            start = self.racks_in_loading_zone + 1
            end = self.racks_in_loading_zone + self.racks_in_unloading_zone
            lines.append(f"\nЗОНА ВЫГРУЗКИ ({start}-{end}):")
            for position, rack in self.get_unloader_zone_status():
                if rack is None:
                    lines.append(f"  {position}: [ПУСТО]")
                    continue
                lines.append(f"  {position}: Рэk {rack.name} — {rack.get_tube_count()}/{rack.MAX_TUBES}")

            try:
                total_unloader = self.get_total_tubes_in_unloader_zone()
            except Exception:
                total_unloader = 0
            lines.append(f"Итого пробирок в зоне выгрузки: {total_unloader}")

            # ===== MINDRAY =====
            mindray_count = self.get_mindray_racks_count()
            try:
                total_mindray = self.get_total_tubes_in_mindray()
            except Exception:
                total_mindray = 0

            lines.append(f"\nMINDRAY CL-6000i: рэков = {mindray_count}")
            lines.append(f"Итого пробирок в MindRay: {total_mindray}")

            return "\n".join(lines)

