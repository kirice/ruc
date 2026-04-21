"""
GUI Dashboard - Панель управления, консоли, переключатель режимов, визуализация предсказаний
"""

import logging
import threading
import time
from pathlib import Path
from typing import Optional, Dict, Any, List, Callable
from dataclasses import dataclass
from enum import Enum

try:
    import tkinter as tk
    from tkinter import ttk, scrolledtext
    TK_AVAILABLE = True
except ImportError:
    TK_AVAILABLE = False


class DashboardMode(Enum):
    """Режимы работы дашборда"""
    NORMAL = "normal"           # Обычный режим
    TRAINING = "training"       # Режим записи данных
    DEBUG = "debug"            # Отладочный режим
    MINIMAL = "minimal"        # Минимальный интерфейс


@dataclass
class PredictionMarker:
    """Маркер предсказания для визуализации"""
    x: float
    y: float
    confidence: float
    timestamp: float


class Dashboard:
    """Панель управления ботом"""
    
    def __init__(self, scheduler, state_machine, config: dict = None):
        self.scheduler = scheduler
        self.state_machine = state_machine
        self.config = config or {}
        
        self.logger = logging.getLogger("dashboard")
        
        # Состояние
        self._running = False
        self._mode = DashboardMode.NORMAL
        self._active_bot_id: Optional[str] = None
        
        # Данные для визуализации
        self._predictions: List[PredictionMarker] = []
        self._max_predictions = 100
        
        # Callbacks
        self._update_callbacks: List[Callable] = []
        
        # GUI элементы (если используются)
        self._root: Optional[tk.Tk] = None
        self._console1_widget = None
        self._console2_widget = None
        self._status_label = None
        self._metrics_label = None
        
        self.logger.info("Dashboard инициализирован")
    
    def start(self):
        """Запуск дашборда"""
        if self._running:
            return
        
        self._running = True
        self.logger.info("Dashboard запущен")
        
        # Запуск в отдельном потоке если GUI доступен
        if TK_AVAILABLE and self.config.get("gui", {}).get("enabled", True):
            self._start_gui_thread()
    
    def stop(self):
        """Остановка дашборда"""
        self._running = False
        if self._root:
            try:
                self._root.quit()
                self._root.destroy()
            except:
                pass
        self.logger.info("Dashboard остановлен")
    
    def _start_gui_thread(self):
        """Запуск GUI в отдельном потоке"""
        gui_thread = threading.Thread(target=self._run_gui, daemon=True)
        gui_thread.start()
    
    def _run_gui(self):
        """Основной цикл GUI"""
        if not TK_AVAILABLE:
            self.logger.warning("Tkinter недоступен, GUI не будет показан")
            return
        
        try:
            self._root = tk.Tk()
            self._root.title("Bot Control Dashboard")
            self._root.geometry("800x600")
            
            self._build_ui()
            
            # Периодическое обновление
            self._schedule_updates()
            
            self._root.mainloop()
        except Exception as e:
            self.logger.error(f"Ошибка GUI: {e}", exc_info=True)
    
    def _build_ui(self):
        """Построение интерфейса"""
        # Верхняя панель
        top_frame = ttk.Frame(self._root)
        top_frame.pack(fill=tk.X, padx=5, pady=5)
        
        # Выбор бота
        ttk.Label(top_frame, text="Бот:").pack(side=tk.LEFT)
        self._bot_combo = ttk.Combobox(top_frame, width=20)
        self._bot_combo.pack(side=tk.LEFT, padx=5)
        self._bot_combo.bind('<<ComboboxSelected>>', self._on_bot_selected)
        
        # Статус
        self._status_label = ttk.Label(top_frame, text="Статус: Ожидание", foreground="gray")
        self._status_label.pack(side=tk.RIGHT, padx=10)
        
        # Консоли
        consoles_frame = ttk.Frame(self._root)
        consoles_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # Консоль 1 - Флуд
        floyd_frame = ttk.LabelFrame(consoles_frame, text="Консоль 1 (Флуд-команды)")
        floyd_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=2)
        
        self._console1_widget = scrolledtext.ScrolledText(floyd_frame, height=10, width=40)
        self._console1_widget.pack(fill=tk.BOTH, expand=True, padx=2, pady=2)
        
        ttk.Button(floyd_frame, text="Отправить", command=self._send_console1).pack(pady=2)
        
        # Консоль 2 - Системная
        system_frame = ttk.LabelFrame(consoles_frame, text="Консоль 2 (Системные команды)")
        system_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=2)
        
        self._console2_widget = scrolledtext.ScrolledText(system_frame, height=10, width=40)
        self._console2_widget.pack(fill=tk.BOTH, expand=True, padx=2, pady=2)
        
        ttk.Button(system_frame, text="Отправить", command=self._send_console2).pack(pady=2)
        
        # Нижняя панель с метриками
        bottom_frame = ttk.Frame(self._root)
        bottom_frame.pack(fill=tk.X, padx=5, pady=5)
        
        self._metrics_label = ttk.Label(bottom_frame, text="FPS: 0 | Предсказаний: 0")
        self._metrics_label.pack(side=tk.LEFT)
        
        # Переключатель режима
        mode_frame = ttk.Frame(bottom_frame)
        mode_frame.pack(side=tk.RIGHT)
        
        ttk.Label(mode_frame, text="Режим:").pack(side=tk.LEFT)
        self._mode_var = tk.StringVar(value="normal")
        mode_combo = ttk.Combobox(mode_frame, textvariable=self._mode_var, width=15)
        mode_combo['values'] = ('normal', 'training', 'debug', 'minimal')
        mode_combo.pack(side=tk.LEFT, padx=5)
        mode_combo.bind('<<ComboboxSelected>>', self._on_mode_changed)
    
    def _schedule_updates(self):
        """Периодическое обновление интерфейса"""
        if self._root and self._running:
            self._update_ui()
            self._root.after(100, self._schedule_updates)
    
    def _update_ui(self):
        """Обновление элементов интерфейса"""
        try:
            # Обновление статуса
            if self._active_bot_id:
                profile = self.state_machine.get_profile(self._active_bot_id)
                if profile:
                    status_text = f"Статус: {profile.state.value}"
                    color = "green" if profile.state == "running" else "orange"
                    self._status_label.config(text=status_text, foreground=color)
            
            # Обновление метрик
            if self.scheduler:
                stats = self.scheduler.get_queue_stats()
                metrics_text = f"Очереди: H={stats['high_priority']} L={stats['low_priority']} A={stats['action']} | Ботов: {stats['active_bots']}"
                self._metrics_label.config(text=metrics_text)
            
            # Обновление списка ботов
            profiles = self.state_machine.get_all_profiles()
            bot_ids = [p.bot_id for p in profiles]
            if bot_ids:
                self._bot_combo['values'] = bot_ids
                if not self._active_bot_id:
                    self._active_bot_id = bot_ids[0]
                    self._bot_combo.set(self._active_bot_id)
                    
        except Exception as e:
            self.logger.debug(f"Ошибка обновления UI: {e}")
    
    def _on_bot_selected(self, event):
        """Выбор активного бота"""
        selected = self._bot_combo.get()
        if selected:
            self._active_bot_id = selected
            self.logger.info(f"Выбран бот: {selected}")
    
    def _on_mode_changed(self, event):
        """Смена режима работы"""
        mode_str = self._mode_var.get()
        self._mode = DashboardMode(mode_str)
        self.logger.info(f"Режим изменён на: {mode_str}")
    
    def _send_console1(self):
        """Отправка команды из консоли 1 (флуд)"""
        if self._console1_widget:
            command = self._console1_widget.get("1.0", tk.END).strip()
            if command:
                self.scheduler.submit_console_command(command, console_id=1)
                self._console1_widget.delete("1.0", tk.END)
    
    def _send_console2(self):
        """Отправка команды из консоли 2 (системная)"""
        if self._console2_widget:
            command = self._console2_widget.get("1.0", tk.END).strip()
            if command:
                self.scheduler.submit_console_command(command, console_id=2)
                self._console2_widget.delete("1.0", tk.END)
    
    def add_prediction(self, x: float, y: float, confidence: float):
        """Добавление предсказания для визуализации"""
        marker = PredictionMarker(x=x, y=y, confidence=confidence, timestamp=time.time())
        self._predictions.append(marker)
        
        # Ограничение количества
        if len(self._predictions) > self._max_predictions:
            self._predictions = self._predictions[-self._max_predictions:]
    
    def get_predictions(self) -> List[PredictionMarker]:
        """Получение последних предсказаний"""
        return self._predictions.copy()
    
    def set_mode(self, mode: DashboardMode):
        """Установка режима работы"""
        self._mode = mode
        self.logger.info(f"Режим установлен: {mode.name}")
    
    def get_mode(self) -> DashboardMode:
        """Получение текущего режима"""
        return self._mode
    
    def log_message(self, message: str, level: str = "info"):
        """Логирование сообщения в консоль"""
        if self._console1_widget:
            timestamp = time.strftime("%H:%M:%S")
            self._console1_widget.insert(tk.END, f"[{timestamp}] {message}\n")
            self._console1_widget.see(tk.END)


class TrainerOverlay:
    """Визуальный интерфейс для режима записи пар «скрин→клик»"""
    
    def __init__(self, dashboard: Dashboard, trainer_callback=None):
        self.dashboard = dashboard
        self.trainer_callback = trainer_callback
        self.logger = logging.getLogger("trainer_overlay")
        
        self._recording = False
        self._current_frame = None
        self._pending_click = None
    
    def start_recording(self):
        """Начать запись пары скрин→клик"""
        self._recording = True
        self.dashboard.set_mode(DashboardMode.TRAINING)
        self.logger.info("Запись пар начата")
    
    def stop_recording(self):
        """Остановить запись"""
        self._recording = False
        self.dashboard.set_mode(DashboardMode.NORMAL)
        self.logger.info("Запись пар остановлена")
    
    def on_frame_capture(self, frame):
        """Обработка захваченного кадра в режиме записи"""
        if self._recording:
            self._current_frame = frame
    
    def on_click(self, x: int, y: int):
        """Обработка клика пользователя в режиме записи"""
        if self._recording and self._current_frame is not None:
            self._pending_click = (x, y)
            self.logger.info(f"Клик зафиксирован: ({x}, {y})")
            
            # Сохранение пары
            if self.trainer_callback:
                self.trainer_callback(self._current_frame, x, y)
    
    def is_recording(self) -> bool:
        """Проверка активности записи"""
        return self._recording
