# src/mindray_automation_2/orchestration/runtime/robots/errors/iteration_exceptions.py
class IterationAbort(Exception):
    pass

class IterationTimeout(IterationAbort):
    """Прерывание по таймауту ожидания"""
    pass

class IterationStopped(IterationAbort):
    """Прерывание по stop_event (внешняя остановка)"""
    pass