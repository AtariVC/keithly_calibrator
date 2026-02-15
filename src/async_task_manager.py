import asyncio
import logging
from collections.abc import Coroutine
from typing import Any, Dict, List, Optional, Callable
from logging import Logger
import qasync

class PrintLogger:
    """Заменяет стандартный логгер, имитируя его интерфейс"""
    def __call__(self, message: str, level: str = "INFO") -> None:
        print(f"[{level.upper()}] {message}")

    def __getattr__(self, level: str) -> Callable[[str], None]:
        # Для поддержки logger.warning() и других методов
        return lambda msg: self(msg, level)

class AsyncTaskManager:
    """
    Менеджер асинхронных задач: создаёт, отслеживает, отменяет.
    """
    def __init__(self, logger: Optional[Logger] = None) -> None:
        self.tasks: Dict[str, asyncio.Task] = {}
        # Делаем logger вызываемым объектом
        self.logger = logger if logger is not None else PrintLogger()


    def create_task(self, coroutine: Coroutine[Any, Any, Any], task_name: str) -> None:
        """
        Создаёт задачу, если она ещё не активна.
        :param coroutine: вызванная корутина
        :param task_name: уникальное имя задачи
        """
        existing_task = self.tasks.get(task_name)
        if existing_task and not existing_task.done():
            self.logger.warning(f"Задача '{task_name}' уже выполняется")
            return

        try:
            task = asyncio.create_task(coroutine)
            self.tasks[task_name] = task
            task.add_done_callback(lambda t: self._handle_task_completion(t, task_name))
            self.logger.info(f"Задача '{task_name}' запущена")
        except Exception as e:
            self.logger.warning(f"Ошибка при запуске задачи '{task_name}': {e}")

    def cancel_task(self, task_name: str) -> None:
        """
        Отменяет задачу по имени.
        :param task_name: имя задачи
        """
        task = self.tasks.get(task_name)
        if task and not task.done():
            task.cancel()
        else:
            self.logger.debug(f"Задача '{task_name}' не найдена или уже завершена")

    def cancel_all_tasks(self) -> None:
        """
        Отменяет все активные задачи.
        """
        for name, task in list(self.tasks.items()):
            if not task.done():
                task.cancel()
                self.logger.info(f"Задача '{name}' отменена (массовая отмена)")
        self.tasks.clear()

    def get_active_tasks(self) -> List[str]:
        """
        Возвращает список имён активных (не завершённых) задач.
        :return: список строк с именами задач
        """
        return [name for name, task in self.tasks.items() if not task.done()]

    def _handle_task_completion(self, task: asyncio.Task, task_name: str):
        try:
            if task.cancelled():
                self.logger.debug(f"Задача {task_name} отменена")
            elif exc := task.exception():
                self.logger.error(f"Ошибка в {task_name}: {exc}")
            else:
                # Безопасно получаем результат только для успешных задач
                result = task.result()
                self.logger.debug(f"Задача {task_name} завершена: {result}")
        except Exception as e:
            self.logger.error(f"Ошибка обработки завершения: {e}")
        finally:
            self.tasks.pop(task_name, None)