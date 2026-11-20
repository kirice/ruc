"""
State Machine - Хранит текущее состояние каждого профиля, валидирует переходы между состояниями
"""

import logging
import threading
from pathlib import Path
from typing import Dict, Any, Optional, List, Callable
from enum import Enum
from dataclasses import dataclass, field
import time
import json


class BotState(Enum):
    """Состояния бота"""
    IDLE = "idle"               # Ожидание
    RUNNING = "running"         # Активная работа
    PAUSED = "paused"           # Пауза
    ERROR = "error"             # Ошибка
    STOPPED = "stopped"         # Остановлен
    CALIBRATING = "calibrating" # Калибровка
    WAITING = "waiting"         # Ожидание события


class StateTransition(Enum):
    """Допустимые переходы между состояниями"""
    START = "start"
    STOP = "stop"
    PAUSE = "pause"
    RESUME = "resume"
    ERROR_OCCURRED = "error"
    RECOVER = "recover"
    CALIBRATE = "calibrate"


# Карта допустимых переходов
VALID_TRANSITIONS = {
    BotState.IDLE: [StateTransition.START, StateTransition.CALIBRATE],
    BotState.RUNNING: [StateTransition.PAUSE, StateTransition.STOP, StateTransition.ERROR_OCCURRED],
    BotState.PAUSED: [StateTransition.RESUME, StateTransition.STOP, StateTransition.ERROR_OCCURRED],
    BotState.ERROR: [StateTransition.RECOVER, StateTransition.STOP],
    BotState.STOPPED: [StateTransition.START, StateTransition.CALIBRATE],
    BotState.CALIBRATING: [StateTransition.START, StateTransition.ERROR_OCCURRED],
    BotState.WAITING: [StateTransition.START, StateTransition.STOP, StateTransition.ERROR_OCCURRED],
}


@dataclass
class BotProfile:
    """Профиль бота"""
    bot_id: str
    name: str
    state: BotState = BotState.IDLE
    config_path: str = ""
    map_id: str = ""
    created_at: float = field(default_factory=time.time)
    last_state_change: float = field(default_factory=time.time)
    error_message: str = ""
    metrics: Dict[str, Any] = field(default_factory=dict)


class StateMachine:
    """Машина состояний для управления профилями ботов"""
    
    def __init__(self, config: dict = None):
        self.config = config or {}
        self.logger = logging.getLogger("state_machine")
        
        # Профили ботов
        self._profiles: Dict[str, BotProfile] = {}
        self._lock = threading.Lock()
        
        # Callbacks для уведомлений о смене состояния
        self._state_callbacks: List[Callable[[str, BotState, BotState], None]] = []
        
        # Пути
        self.bots_config_dir = Path(self.config.get("paths", {}).get(
            "bots_config_dir", "config/bots"
        ))
        
        self.logger.info("StateMachine инициализирован")
    
    def create_profile(self, bot_id: str, name: str, config_path: str = "", 
                       map_id: str = "") -> BotProfile:
        """
        Создание нового профиля бота
        
        Args:
            bot_id: Уникальный идентификатор
            name: Отображаемое имя
            config_path: Путь к конфигурации
            map_id: ID карты по умолчанию
            
        Returns:
            Созданный профиль
        """
        with self._lock:
            if bot_id in self._profiles:
                raise ValueError(f"Профиль {bot_id} уже существует")
            
            profile = BotProfile(
                bot_id=bot_id,
                name=name,
                config_path=config_path,
                map_id=map_id
            )
            
            self._profiles[bot_id] = profile
            
            # Загрузка конфигурации если указана
            if config_path:
                self._load_profile_config(profile)
            
            self.logger.info(f"Профиль создан: {bot_id}")
            return profile
    
    def delete_profile(self, bot_id: str):
        """Удаление профиля"""
        with self._lock:
            if bot_id not in self._profiles:
                raise ValueError(f"Профиль {bot_id} не найден")
            
            profile = self._profiles[bot_id]
            if profile.state == BotState.RUNNING:
                raise ValueError(f"Нельзя удалить активный профиль {bot_id}")
            
            del self._profiles[bot_id]
            self.logger.info(f"Профиль удален: {bot_id}")
    
    def get_profile(self, bot_id: str) -> Optional[BotProfile]:
        """Получение профиля"""
        return self._profiles.get(bot_id)
    
    def get_all_profiles(self) -> List[BotProfile]:
        """Получение всех профилей"""
        return list(self._profiles.values())
    
    def transition(self, bot_id: str, transition: StateTransition) -> bool:
        """
        Выполнение перехода состояния
        
        Args:
            bot_id: ID бота
            transition: Тип перехода
            
        Returns:
            True если переход успешен
        """
        with self._lock:
            if bot_id not in self._profiles:
                self.logger.error(f"Профиль {bot_id} не найден")
                return False
            
            profile = self._profiles[bot_id]
            old_state = profile.state
            
            # Проверка допустимости перехода
            valid_transitions = VALID_TRANSITIONS.get(old_state, [])
            if transition not in valid_transitions:
                self.logger.warning(
                    f"Недопустимый переход {transition.name} из состояния {old_state.name}"
                )
                return False
            
            # Выполнение перехода
            new_state = self._apply_transition(old_state, transition)
            profile.state = new_state
            profile.last_state_change = time.time()
            
            self.logger.info(f"Переход: {bot_id} {old_state.name} -> {new_state.name}")
            
            # Уведомление callbacks
            for callback in self._state_callbacks:
                try:
                    callback(bot_id, old_state, new_state)
                except Exception as e:
                    self.logger.error(f"Ошибка callback состояния: {e}")
            
            return True
    
    def _apply_transition(self, current_state: BotState, 
                          transition: StateTransition) -> BotState:
        """Применение перехода к состоянию"""
        transition_map = {
            StateTransition.START: BotState.RUNNING,
            StateTransition.STOP: BotState.STOPPED,
            StateTransition.PAUSE: BotState.PAUSED,
            StateTransition.RESUME: BotState.RUNNING,
            StateTransition.ERROR_OCCURRED: BotState.ERROR,
            StateTransition.RECOVER: BotState.IDLE,
            StateTransition.CALIBRATE: BotState.CALIBRATING,
        }
        return transition_map.get(transition, current_state)
    
    def set_error(self, bot_id: str, error_message: str):
        """Установка состояния ошибки"""
        with self._lock:
            if bot_id in self._profiles:
                profile = self._profiles[bot_id]
                profile.state = BotState.ERROR
                profile.error_message = error_message
                profile.last_state_change = time.time()
                
                self.logger.error(f"Ошибка бота {bot_id}: {error_message}")
    
    def update_metrics(self, bot_id: str, metrics: Dict[str, Any]):
        """Обновление метрик бота"""
        with self._lock:
            if bot_id in self._profiles:
                self._profiles[bot_id].metrics.update(metrics)
    
    def register_state_callback(self, callback: Callable[[str, BotState, BotState], None]):
        """Регистрация callback'а для уведомлений о смене состояния"""
        self._state_callbacks.append(callback)
    
    def _load_profile_config(self, profile: BotProfile):
        """Загрузка конфигурации профиля"""
        try:
            config_path = Path(profile.config_path)
            if config_path.exists():
                with open(config_path, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                profile.metrics["config_loaded"] = True
                self.logger.debug(f"Конфигурация загружена для {profile.bot_id}")
        except Exception as e:
            self.logger.warning(f"Не удалось загрузить конфиг для {profile.bot_id}: {e}")
            profile.metrics["config_loaded"] = False
    
    def save_profile(self, bot_id: str) -> bool:
        """Сохранение профиля в файл"""
        with self._lock:
            if bot_id not in self._profiles:
                return False
            
            profile = self._profiles[bot_id]
            
            # Создание директории если нет
            self.bots_config_dir.mkdir(parents=True, exist_ok=True)
            
            # Сохранение
            config_file = self.bots_config_dir / f"profile_{bot_id}.json"
            
            data = {
                "bot_id": profile.bot_id,
                "name": profile.name,
                "state": profile.state.value,
                "config_path": profile.config_path,
                "map_id": profile.map_id,
                "created_at": profile.created_at,
                "last_state_change": profile.last_state_change,
                "metrics": profile.metrics
            }
            
            with open(config_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            
            self.logger.info(f"Профиль сохранен: {config_file}")
            return True
    
    def load_profile(self, bot_id: str, config_file: str) -> bool:
        """Загрузка профиля из файла"""
        try:
            with open(config_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            with self._lock:
                profile = BotProfile(
                    bot_id=data["bot_id"],
                    name=data["name"],
                    state=BotState(data.get("state", "idle")),
                    config_path=data.get("config_path", ""),
                    map_id=data.get("map_id", ""),
                    created_at=data.get("created_at", time.time()),
                    last_state_change=data.get("last_state_change", time.time()),
                    metrics=data.get("metrics", {})
                )
                
                self._profiles[bot_id] = profile
            
            self.logger.info(f"Профиль загружен: {config_file}")
            return True
            
        except Exception as e:
            self.logger.error(f"Ошибка загрузки профиля: {e}")
            return False
    
    def get_state(self, bot_id: str) -> Optional[BotState]:
        """Получение текущего состояния бота"""
        profile = self._profiles.get(bot_id)
        return profile.state if profile else None
    
    def is_running(self, bot_id: str) -> bool:
        """Проверка запущен ли бот"""
        return self.get_state(bot_id) == BotState.RUNNING
    
    def is_active(self, bot_id: str) -> bool:
        """Проверка активности бота (не stopped и не error)"""
        state = self.get_state(bot_id)
        return state not in (BotState.STOPPED, BotState.ERROR)
    
    def get_statistics(self) -> Dict[str, Any]:
        """Статистика по всем профилям"""
        with self._lock:
            states_count = {}
            for state in BotState:
                states_count[state.value] = 0
            
            for profile in self._profiles.values():
                states_count[profile.state.value] += 1
            
            return {
                "total_profiles": len(self._profiles),
                "states": states_count
            }
