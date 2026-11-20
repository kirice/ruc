"""
Consoles - Реализует две изолированные очереди ввода, переключатель приоритетов, фильтрацию дубликатов команд
"""

import logging
import threading
import time
from typing import Optional, Dict, Any, List, Callable, Set
from dataclasses import dataclass, field
from enum import Enum
from collections import deque


class ConsoleType(Enum):
    """Типы консолей"""
    FLOOD = 1       # Флуд-команды (низкий приоритет)
    SYSTEM = 2      # Системные команды (высокий приоритет)


@dataclass
class ConsoleCommand:
    """Команда консоли"""
    command_str: str
    console_type: ConsoleType
    timestamp: float = field(default_factory=time.time)
    source: str = "user"
    
    def parse(self) -> tuple:
        """Парсинг команды на имя и аргументы"""
        parts = self.command_str.strip().split(maxsplit=1)
        cmd_name = parts[0].lower() if parts else ""
        cmd_args = parts[1].split() if len(parts) > 1 else []
        return cmd_name, cmd_args


class ConsolesManager:
    """Менеджер двух консолей ввода"""
    
    def __init__(self, scheduler, config: dict = None):
        self.scheduler = scheduler
        self.config = config or {}
        
        self.logger = logging.getLogger("consoles")
        
        # Очереди команд
        self._flood_queue: deque = deque()
        self._system_queue: deque = deque()
        
        # Блокировка
        self._lock = threading.Lock()
        
        # Фильтр дубликатов
        self._recent_commands: Set[str] = set()
        self._max_recent = 100
        self._duplicate_window = config.get("consoles", {}).get("duplicate_window", 5.0)
        
        # Статистика
        self._stats = {
            "flood_commands": 0,
            "system_commands": 0,
            "duplicates_filtered": 0
        }
        
        # Callbacks
        self.on_command_added: Optional[Callable[[ConsoleCommand], None]] = None
        
        self.logger.info("ConsolesManager инициализирован")
    
    def add_command(self, command_str: str, console_type: ConsoleType, source: str = "user") -> bool:
        """
        Добавление команды в очередь
        
        Args:
            command_str: Строка команды
            console_type: Тип консоли
            source: Источник команды
            
        Returns:
            True если команда добавлена
        """
        # Проверка на дубликаты
        if self._is_duplicate(command_str):
            self._stats["duplicates_filtered"] += 1
            self.logger.debug(f"Дубликат команды отфильтрован: {command_str}")
            return False
        
        command = ConsoleCommand(
            command_str=command_str,
            console_type=console_type,
            source=source
        )
        
        with self._lock:
            if console_type == ConsoleType.FLOOD:
                self._flood_queue.append(command)
                self._stats["flood_commands"] += 1
                self.logger.debug(f"Флуд-команда добавлена: {command_str}")
            else:
                # Системные команды - в начало очереди
                self._system_queue.appendleft(command)
                self._stats["system_commands"] += 1
                self.logger.info(f"Системная команда добавлена: {command_str}")
            
            # Добавление в recent для фильтрации дубликатов
            self._add_to_recent(command_str)
        
        # Отправка в планировщик
        self._submit_to_scheduler(command)
        
        # Callback
        if self.on_command_added:
            self.on_command_added(command)
        
        return True
    
    def _is_duplicate(self, command_str: str) -> bool:
        """Проверка команды на дубликат"""
        normalized = command_str.strip().lower()
        current_time = time.time()
        
        # Очистка старых записей
        self._cleanup_recent(current_time)
        
        return normalized in self._recent_commands
    
    def _add_to_recent(self, command_str: str):
        """Добавление команды в список недавних"""
        normalized = command_str.strip().lower()
        self._recent_commands.add(normalized)
        
        # Ограничение размера
        if len(self._recent_commands) > self._max_recent:
            # Удаляем случайный элемент (упрощённо)
            while len(self._recent_commands) > self._max_recent:
                self._recent_commands.pop()
    
    def _cleanup_recent(self, current_time: float):
        """Очистка старых записей о дубликатах"""
        # В данной реализации просто ограничиваем количество
        # Можно добавить временные метки для более точной очистки
        pass
    
    def _submit_to_scheduler(self, command: ConsoleCommand):
        """Отправка команды в планировщик"""
        console_id = 1 if command.console_type == ConsoleType.FLOOD else 2
        self.scheduler.submit_console_command(command.command_str, console_id=console_id)
    
    def get_queue_stats(self) -> Dict[str, int]:
        """Статистика очередей"""
        with self._lock:
            return {
                "flood_queue": len(self._flood_queue),
                "system_queue": len(self._system_queue),
                **self._stats
            }
    
    def clear_flood_queue(self):
        """Очистка очереди флуд-команд"""
        with self._lock:
            self._flood_queue.clear()
        self.logger.debug("Очередь флуд-команд очищена")
    
    def clear_system_queue(self):
        """Очистка очереди системных команд"""
        with self._lock:
            self._system_queue.clear()
        self.logger.debug("Очередь системных команд очищена")
    
    def get_pending_commands(self, console_type: ConsoleType) -> List[ConsoleCommand]:
        """Получение ожидающих команд"""
        with self._lock:
            if console_type == ConsoleType.FLOOD:
                return list(self._flood_queue)
            else:
                return list(self._system_queue)
    
    def process_next_command(self, console_type: ConsoleType) -> Optional[ConsoleCommand]:
        """Извлечение следующей команды для выполнения"""
        with self._lock:
            if console_type == ConsoleType.FLOOD:
                if self._flood_queue:
                    return self._flood_queue.popleft()
            else:
                if self._system_queue:
                    return self._system_queue.popleft()
        return None


class CommandFilter:
    """Фильтр команд для предотвращения нежелательных действий"""
    
    def __init__(self, config: dict = None):
        self.config = config or {}
        self.logger = logging.getLogger("command_filter")
        
        # Запрещённые команды
        self._blocked_commands: Set[str] = set(
            self.config.get("consoles", {}).get("blocked_commands", [])
        )
        
        # Разрешённые команды для флуд-консоли
        allowed_flood = self.config.get("consoles", {}).get("allowed_flood_commands", [
            "move", "click", "wait", "repeat"
        ])
        self._allowed_flood: Set[str] = set(allowed_flood)
        
        # Лимит повторений
        self._repeat_limit = self.config.get("consoles", {}).get("repeat_limit", 10)
        self._repeat_counts: Dict[str, int] = {}
    
    def is_allowed(self, command: ConsoleCommand) -> bool:
        """Проверка разрешена ли команда"""
        cmd_name, _ = command.parse()
        
        # Проверка заблокированных команд
        if cmd_name in self._blocked_commands:
            self.logger.warning(f"Заблокированная команда: {cmd_name}")
            return False
        
        # Проверка для флуд-консоли
        if command.console_type == ConsoleType.FLOOD:
            if cmd_name not in self._allowed_flood:
                self.logger.warning(f"Команда недоступна для флуд-консоли: {cmd_name}")
                return False
            
            # Проверка лимита повторений
            self._repeat_counts[cmd_name] = self._repeat_counts.get(cmd_name, 0) + 1
            if self._repeat_counts[cmd_name] > self._repeat_limit:
                self.logger.warning(f"Превышен лимит повторений для {cmd_name}")
                return False
        
        return True
    
    def reset_repeat_counts(self):
        """Сброс счётчиков повторений"""
        self._repeat_counts.clear()
    
    def add_blocked_command(self, command: str):
        """Добавление команды в чёрный список"""
        self._blocked_commands.add(command.lower())
        self.logger.info(f"Команда добавлена в чёрный список: {command}")
    
    def remove_blocked_command(self, command: str):
        """Удаление команды из чёрного списка"""
        self._blocked_commands.discard(command.lower())
        self.logger.info(f"Команда удалена из чёрного списка: {command}")
