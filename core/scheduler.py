"""
Scheduler - Управляет очередями задач, распределяет ресурсы CPU/GPU между активными ботами, 
обрабатывает приоритеты команд
"""

import logging
import threading
import time
from pathlib import Path
from typing import Dict, Any, Optional, List, Callable
from collections import deque
from dataclasses import dataclass, field
from enum import Enum


class CommandPriority(Enum):
    """Приоритеты команд"""
    LOW = 0      # Флуд-команды
    NORMAL = 1   # Обычные действия бота
    HIGH = 2     # Системные команды
    CRITICAL = 3 # Экстренный стоп


@dataclass
class Command:
    """Команда для выполнения"""
    name: str
    args: tuple = field(default_factory=tuple)
    kwargs: dict = field(default_factory=dict)
    priority: CommandPriority = CommandPriority.NORMAL
    timestamp: float = field(default_factory=time.time)
    source: str = "system"  # "console1", "console2", "bot", "system"
    
    def __lt__(self, other):
        # Для сортировки в priority queue - более высокий приоритет первый
        return self.priority.value > other.priority.value


class Scheduler:
    """Центральный диспетчер задач и ресурсов"""
    
    def __init__(self, config: dict = None):
        self.config = config or {}
        self.logger = logging.getLogger("scheduler")
        
        # Очереди команд
        self._high_priority_queue: deque = deque()  # Системные команды
        self._low_priority_queue: deque = deque()   # Флуд-команды
        self._action_queue: deque = deque()         # Действия бота
        
        # Блокировки
        self._queue_lock = threading.Lock()
        self._execution_lock = threading.Lock()
        
        # Состояние
        self._running = False
        self._paused = False
        self._executing_command = False
        
        # Активные боты и их ресурсы
        self._active_bots: Dict[str, Dict[str, Any]] = {}
        self._resource_allocation: Dict[str, float] = {}  # bot_id -> % CPU
        
        # Callbacks
        self.on_command_executed: Optional[Callable] = None
        
        # Настройки
        sched_config = self.config.get("scheduler", {})
        self.max_cpu_usage = sched_config.get("max_cpu_usage", 80.0)
        self.command_timeout = sched_config.get("command_timeout", 5.0)
        
        # Поток выполнения
        self._executor_thread: Optional[threading.Thread] = None
        
        self.logger.info("Scheduler инициализирован")
    
    def start(self):
        """Запуск планировщика"""
        if self._running:
            return
        
        self._running = True
        self._paused = False
        self._executor_thread = threading.Thread(target=self._execute_loop, daemon=True)
        self._executor_thread.start()
        self.logger.info("Scheduler запущен")
    
    def stop(self):
        """Остановка планировщика"""
        self._running = False
        if self._executor_thread:
            self._executor_thread.join(timeout=5)
        self.logger.info("Scheduler остановлен")
    
    def pause(self):
        """Пауза выполнения"""
        self._paused = True
        self.logger.info("Scheduler на паузе")
    
    def resume(self):
        """Возобновление выполнения"""
        self._paused = False
        self.logger.info("Scheduler возобновлен")
    
    def submit_command(self, command: Command):
        """
        Отправка команды в очередь
        
        Args:
            command: Команда для выполнения
        """
        with self._queue_lock:
            if command.priority == CommandPriority.CRITICAL or command.priority == CommandPriority.HIGH:
                # Системные команды - немедленное выполнение
                self.logger.info(f"Системная команда: {command.name}")
                self._high_priority_queue.appendleft(command)
                # Прерываем текущее выполнение
                self._executing_command = False
            elif command.priority == CommandPriority.LOW:
                # Флуд-команды - низкий приоритет
                self._low_priority_queue.append(command)
            else:
                # Обычные команды
                self._action_queue.append(command)
            
            self.logger.debug(f"Команда добавлена: {command.name} (priority={command.priority.name})")
    
    def submit_console_command(self, command_str: str, console_id: int = 1):
        """
        Отправка команды из консоли
        
        Args:
            command_str: Строка команды
            console_id: ID консоли (1 = флуд, 2 = системная)
        """
        priority = CommandPriority.LOW if console_id == 1 else CommandPriority.HIGH
        source = "console1" if console_id == 1 else "console2"
        
        # Парсинг команды
        parts = command_str.strip().split(maxsplit=1)
        if not parts:
            return
        
        cmd_name = parts[0].lower()
        cmd_args = parts[1].split() if len(parts) > 1 else []
        
        command = Command(
            name=cmd_name,
            args=tuple(cmd_args),
            priority=priority,
            source=source
        )
        
        self.submit_command(command)
        self.logger.info(f"Консоль {console_id}: {command_str}")
    
    def _execute_loop(self):
        """Цикл выполнения команд"""
        while self._running:
            try:
                if self._paused:
                    time.sleep(0.1)
                    continue
                
                command = self._get_next_command()
                
                if command:
                    self._execute_command(command)
                else:
                    time.sleep(0.01)  # Минимальная задержка
                    
            except Exception as e:
                self.logger.error(f"Ошибка в цикле выполнения: {e}", exc_info=True)
                time.sleep(0.5)
    
    def _get_next_command(self) -> Optional[Command]:
        """Получение следующей команды по приоритету"""
        with self._queue_lock:
            # Сначала проверяем высокоприоритетную очередь
            if self._high_priority_queue:
                return self._high_priority_queue.popleft()
            
            # Затем обычные действия бота
            if self._action_queue:
                return self._action_queue.popleft()
            
            # В последнюю очередь - флуд
            if self._low_priority_queue:
                return self._low_priority_queue.popleft()
        
        return None
    
    def _execute_command(self, command: Command):
        """Выполнение команды"""
        with self._execution_lock:
            self._executing_command = True
            
            try:
                self.logger.info(f"Выполнение: {command.name} (из {command.source})")
                
                # Обработка встроенных команд
                if command.name == "stop":
                    self._handle_stop_command(command)
                elif command.name == "pause":
                    self._handle_pause_command(command)
                elif command.name == "resume":
                    self._handle_resume_command(command)
                elif command.name == "reset":
                    self._handle_reset_command(command)
                else:
                    # Пользовательская команда - вызов callback
                    if self.on_command_executed:
                        self.on_command_executed(command)
                
                self.logger.debug(f"Команда выполнена: {command.name}")
                
            except Exception as e:
                self.logger.error(f"Ошибка выполнения команды {command.name}: {e}")
            finally:
                self._executing_command = False
    
    def _handle_stop_command(self, command: Command):
        """Обработка команды остановки"""
        self.logger.warning("Получена команда STOP")
        self.pause()
    
    def _handle_pause_command(self, command: Command):
        """Обработка команды паузы"""
        self.pause()
    
    def _handle_resume_command(self, command: Command):
        """Обработка команды возобновления"""
        self.resume()
    
    def _handle_reset_command(self, command: Command):
        """Обработка команды сброса"""
        self.logger.info("Сброс очередей")
        with self._queue_lock:
            self._high_priority_queue.clear()
            self._low_priority_queue.clear()
            self._action_queue.clear()
    
    def register_bot(self, bot_id: str, config: dict):
        """
        Регистрация бота в планировщике
        
        Args:
            bot_id: Уникальный идентификатор бота
            config: Конфигурация бота
        """
        with self._queue_lock:
            self._active_bots[bot_id] = {
                "config": config,
                "state": "active",
                "last_action": time.time()
            }
            self._resource_allocation[bot_id] = 100.0 / max(1, len(self._active_bots))
        
        self.logger.info(f"Бот зарегистрирован: {bot_id}")
    
    def unregister_bot(self, bot_id: str):
        """Удаление бота из планировщика"""
        with self._queue_lock:
            if bot_id in self._active_bots:
                del self._active_bots[bot_id]
                del self._resource_allocation[bot_id]
                # Перераспределение ресурсов
                if self._active_bots:
                    new_allocation = 100.0 / len(self._active_bots)
                    for bid in self._active_bots:
                        self._resource_allocation[bid] = new_allocation
        
        self.logger.info(f"Бот удален: {bot_id}")
    
    def get_bot_state(self, bot_id: str) -> Optional[Dict[str, Any]]:
        """Получение состояния бота"""
        return self._active_bots.get(bot_id)
    
    def get_queue_stats(self) -> Dict[str, int]:
        """Статистика очередей"""
        with self._queue_lock:
            return {
                "high_priority": len(self._high_priority_queue),
                "low_priority": len(self._low_priority_queue),
                "action": len(self._action_queue),
                "active_bots": len(self._active_bots)
            }
    
    def is_executing(self) -> bool:
        """Проверка выполнения команды"""
        return self._executing_command
    
    def clear_low_priority_queue(self):
        """Очистка низкоприоритетной очереди (для системных команд)"""
        with self._queue_lock:
            self._low_priority_queue.clear()
        self.logger.debug("Очередь флуд-команд очищена")
