from typing import Optional

class Tripod:
    """
    Родительский класс стандартных штативов
    """
    MIN_TUBES = 0      # MIN кол-во пробирок в паллете
    MAX_TUBES = 50     # MAX кол-во пробирок в паллете

    def __init__(
            self,
            name: str,
            availability: Optional[bool] = False,
    ):
        self.name = name
        self.availability = availability
        self._tubes = None
        # даём возможность иметь свой MAX_TUBES на экземпляр
        self.MAX_TUBES = Tripod.MAX_TUBES

    def set_availability(self, state: bool):
        """Установить доступность паллета"""
        self._tubes = self.MAX_TUBES if state else self._tubes
        self.availability = state
        return state
    
    def _create_palletizing_number(self, prob_number: int) -> int:
        """Создать номер для паллетирования"""
        return self.MAX_TUBES - 1 - prob_number
    
    def get_tubes(self) -> Optional[int]:
        """Вернуть количество пробирок в штативе"""
        return self._tubes

    def set_tubes(self, set_count: int) -> int:
        if not (self.MIN_TUBES <= set_count <= self.MAX_TUBES):
            raise ValueError(f"set_tubes: значение {set_count} вне диапазона 0..{self.MAX_TUBES}")
        self._tubes = set_count
        return self._tubes
    
    def get_empty_places(self) -> int:
        if self.get_tubes() is not None:
            return self.MAX_TUBES - self.get_tubes()
        else:
            return 0
        
    def __str__(self) -> str:
        status = "Пуст или не установлен" if not self.availability else "Установлен"
        return f"Трипод {self.name} (Доступность: {status}, Пробирки: {self._tubes}/{self.MAX_TUBES})"
    

class UnloadingTripod(Tripod):
    """
    Дочерний класс разгружаемых штативов
    """
    def __init__(self, name: str, availability: bool = False):
        super().__init__(name, availability)

    def grab_tube(self) -> Optional[int]:
        """Изъять пробирку из паллета."""
        if not self.availability or self._tubes is None or self._tubes <= self.MIN_TUBES:
            # Тут можешь либо вернуть None, либо поднять исключение — на твой выбор
            return None
        
        self._tubes -= 1

        if self._tubes <= self.MIN_TUBES:
            self.set_availability(False)

        return self._create_palletizing_number(self._tubes)

    
    def __str__(self) -> str:
        status = "Пуст или не установлен" if not self.availability else "Установлен"
        tubes = "" if not self.availability else f", Пробирки: {self._tubes}/{self.MAX_TUBES}"
        return f"Трипод {self.name} — Доступность: {status}{tubes}"


class LoadingTripod(Tripod):
    """
    Дочерний класс загружаемых штативов
    """
    def __init__(self, name: str, availability: bool = False):
        super().__init__(name, availability)

    def set_availability(self, state: bool):
        """Установить доступность паллета"""
        self._tubes = self.MIN_TUBES if state else self._tubes
        self.availability = state
        return state
    
    def _create_palletizing_number(self, prob_number: int) -> int:
        """Создать номер для паллетирования"""
        return prob_number - 1
    
    def place_tube(self) -> Optional[int]:
        """Установить пробирку в паллет."""
        if not self.availability or self._tubes is None or self._tubes >= self.MAX_TUBES:
            return None

        self._tubes += 1

        if self._tubes >= self.MAX_TUBES:
            self.set_availability(False)

        return self._create_palletizing_number(self._tubes)
    
    def __str__(self) -> str:
        status = "Пуст или не установлен" if not self.availability else "Установлен"
        tubes = "" if not self.availability else f", Пробикри: {self._tubes}/{self.MAX_TUBES}"
        return f"Трипод {self.name} — Доступность: {status}{tubes}"