"""
Экран начальной загрузки приложения.

Отображает прогресс инициализации модулей, логотип, версию приложения
и статус загрузки компонентов системы.
"""

import tkinter as tk
from tkinter import ttk
from typing import Optional, Callable
import threading
import time
from pathlib import Path


class SplashScreen:
    """
    Экран начальной загрузки с прогресс-баром и статусами модулей.
    
    Отображает:
    - Логотип/название приложения
    - Версию сборки
    - Прогресс-бар инициализации
    - Список загружаемых модулей со статусами
    - Логи загрузки в реальном времени
    """
    
    def __init__(self, root: Optional[tk.Tk] = None):
        """
        Инициализация экрана загрузки.
        
        Args:
            root: Опциональный существующий Tk root, если нет — создаётся временное окно
        """
        self.root = root if root else tk.Tk()
        self.root.title("Game Bot - Загрузка")
        self.root.geometry("600x400")
        self.root.resizable(False, False)
        self.root.configure(bg="#1a1a2e")
        
        # Центрирование окна на экране
        self._center_window()
        
        # Убираем декорации окна для стиля splash screen
        self.root.overrideredirect(True)
        
        # Переменные состояния
        self.current_step = 0
        self.total_steps = 8
        self.status_messages: list[str] = []
        self.module_statuses: dict[str, str] = {}
        
        # Создание UI элементов
        self._create_widgets()
        
        # Флаг завершения
        self._destroyed = False
    
    def _center_window(self):
        """Центрирует окно на экране."""
        self.root.update_idletasks()
        width = 600
        height = 400
        x = (self.root.winfo_screenwidth() // 2) - (width // 2)
        y = (self.root.winfo_screenheight() // 2) - (height // 2)
        self.root.geometry(f'{width}x{height}+{x}+{y}')
    
    def _create_widgets(self):
        """Создаёт все элементы интерфейса."""
        # Основной фрейм
        main_frame = tk.Frame(self.root, bg="#1a1a2e")
        main_frame.pack(fill=tk.BOTH, expand=True, padx=30, pady=30)
        
        # === Логотип / Название ===
        title_label = tk.Label(
            main_frame,
            text="🤖 GAME BOT",
            font=("Segoe UI", 28, "bold"),
            fg="#00d9ff",
            bg="#1a1a2e"
        )
        title_label.pack(pady=(0, 5))
        
        subtitle_label = tk.Label(
            main_frame,
            text="Система автоматизации игр",
            font=("Segoe UI", 11),
            fg="#8888aa",
            bg="#1a1a2e"
        )
        subtitle_label.pack(pady=(0, 20))
        
        # === Версия ===
        version_label = tk.Label(
            main_frame,
            text="Версия: 0.1.0-alpha | Bot-Full",
            font=("Segoe UI", 9),
            fg="#555577",
            bg="#1a1a2e"
        )
        version_label.pack(anchor=tk.W, pady=(0, 15))
        
        # === Прогресс-бар ===
        progress_frame = tk.Frame(main_frame, bg="#1a1a2e")
        progress_frame.pack(fill=tk.X, pady=10)
        
        self.progress_var = tk.DoubleVar(value=0)
        self.progress_bar = ttk.Progressbar(
            progress_frame,
            variable=self.progress_var,
            maximum=self.total_steps,
            mode='determinate',
            style='blue.Horizontal.TProgressbar'
        )
        self.progress_bar.pack(fill=tk.X, side=tk.TOP, pady=(0, 5))
        
        # Стиль для прогресс-бара
        style = ttk.Style()
        style.theme_use('clam')
        style.configure(
            'blue.Horizontal.TProgressbar',
            troughcolor='#2a2a4e',
            background='#00d9ff',
            bordercolor='#00d9ff',
            lightcolor='#00d9ff',
            darkcolor='#0099cc'
        )
        
        self.progress_label = tk.Label(
            progress_frame,
            text="Инициализация...",
            font=("Segoe UI", 9),
            fg="#aaaaaa",
            bg="#1a1a2e"
        )
        self.progress_label.pack(anchor=tk.W)
        
        # === Список модулей со статусами ===
        modules_frame = tk.Frame(main_frame, bg="#0f0f1e", relief=tk.SUNKEN, bd=1)
        modules_frame.pack(fill=tk.BOTH, expand=True, pady=15)
        
        # Заголовок списка
        header_label = tk.Label(
            modules_frame,
            text="Загрузка модулей:",
            font=("Segoe UI", 10, "bold"),
            fg="#cccccc",
            bg="#0f0f1e",
            anchor=tk.W
        )
        header_label.pack(fill=tk.X, padx=10, pady=8)
        
        # Canvas для прокрутки списка модулей
        self.modules_canvas = tk.Canvas(
            modules_frame,
            bg="#0f0f1e",
            highlightthickness=0
        )
        scrollbar = ttk.Scrollbar(
            modules_frame,
            orient=tk.VERTICAL,
            command=self.modules_canvas.yview
        )
        
        self.modules_inner_frame = tk.Frame(self.modules_canvas, bg="#0f0f1e")
        
        self.modules_canvas.configure(yscrollcommand=scrollbar.set)
        
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.modules_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        self.canvas_window = self.modules_canvas.create_window(
            (0, 0),
            window=self.modules_inner_frame,
            anchor=tk.NW
        )
        
        self.modules_inner_frame.bind("<Configure>", self._on_frame_configure)
        self.modules_canvas.bind("<Configure>", self._on_canvas_configure)
        
        # Инициализация статусов модулей
        self._init_module_status_widgets()
        
        # === Лог загрузки ===
        log_label = tk.Label(
            main_frame,
            text="Лог загрузки:",
            font=("Segoe UI", 9, "bold"),
            fg="#cccccc",
            bg="#1a1a2e",
            anchor=tk.W
        )
        log_label.pack(anchor=tk.W, pady=(10, 5))
        
        self.log_text = tk.Text(
            main_frame,
            height=4,
            font=("Consolas", 8),
            fg="#00ff88",
            bg="#0a0a15",
            wrap=tk.WORD,
            state=tk.DISABLED
        )
        self.log_text.pack(fill=tk.X, pady=(0, 10))
        
        # Настройка тегов для цветов логов
        self.log_text.tag_config("info", foreground="#00ff88")
        self.log_text.tag_config("warning", foreground="#ffaa00")
        self.log_text.tag_config("error", foreground="#ff4444")
    
    def _init_module_status_widgets(self):
        """Инициализирует виджеты статусов модулей."""
        self.module_labels = {}
        
        modules_list = [
            ("Ядро системы", "core_init"),
            ("Менеджер эмулятора", "emulator"),
            ("Нейросеть предиктор (NN-2)", "predictor"),
            ("Нейросеть детектор (NN-1)", "detector"),
            ("Классификатор локаций", "classifier"),
            ("Планировщик задач", "scheduler"),
            ("Интерфейс управления", "gui"),
            ("Система логирования", "logging")
        ]
        
        for i, (name, key) in enumerate(modules_list):
            frame = tk.Frame(self.modules_inner_frame, bg="#0f0f1e")
            frame.pack(fill=tk.X, padx=10, pady=2)
            
            name_label = tk.Label(
                frame,
                text=name,
                font=("Segoe UI", 9),
                fg="#cccccc",
                bg="#0f0f1e",
                anchor=tk.W,
                width=35
            )
            name_label.pack(side=tk.LEFT)
            
            status_label = tk.Label(
                frame,
                text="⏳ Ожидание",
                font=("Segoe UI", 8),
                fg="#ffaa00",
                bg="#0f0f1e",
                anchor=tk.E,
                width=15
            )
            status_label.pack(side=tk.RIGHT)
            
            self.module_labels[key] = status_label
    
    def _on_frame_configure(self, event):
        """Обновляет область прокрутки при изменении размера фрейма."""
        self.modules_canvas.configure(scrollregion=self.modules_canvas.bbox("all"))
    
    def _on_canvas_configure(self, event):
        """Изменяет ширину внутреннего фрейма под canvas."""
        self.modules_canvas.itemconfig(self.canvas_window, width=event.width)
    
    def update_module_status(self, module_key: str, status: str, is_success: bool = True):
        """
        Обновляет статус конкретного модуля.
        
        Args:
            module_key: Ключ модуля из modules_list
            status: Текст статуса (например, "Загружено", "Ошибка")
            is_success: True для успеха (зелёный), False для ошибки (красный)
        """
        if module_key in self.module_labels and not self._destroyed:
            color = "#00ff88" if is_success else "#ff4444"
            icon = "✅" if is_success else "❌"
            
            def _update():
                label = self.module_labels[module_key]
                label.config(text=f"{icon} {status}", fg=color)
            
            self.root.after(0, _update)
    
    def update_progress(self, step: int, message: str = ""):
        """
        Обновляет прогресс-бар и сообщение.
        
        Args:
            step: Текущий шаг (от 0 до total_steps)
            message: Сообщение о текущем этапе
        """
        self.current_step = step
        
        def _update():
            if not self._destroyed:
                self.progress_var.set(step)
                if message:
                    self.progress_label.config(text=message)
        
        self.root.after(0, _update)
    
    def add_log(self, message: str, level: str = "info"):
        """
        Добавляет сообщение в лог загрузки.
        
        Args:
            message: Текст сообщения
            level: Уровень ("info", "warning", "error")
        """
        self.status_messages.append(message)
        
        def _add():
            if not self._destroyed:
                self.log_text.config(state=tk.NORMAL)
                self.log_text.insert(tk.END, f"> {message}\n", level)
                self.log_text.see(tk.END)
                self.log_text.config(state=tk.DISABLED)
        
        self.root.after(0, _add)
    
    def set_version_info(self, version: str, build_type: str):
        """
        Обновляет информацию о версии.
        
        Args:
            version: Строка версии (например, "0.1.0-alpha")
            build_type: Тип сборки (например, "Bot-Full", "Bot-Worker", "Bot-EXE")
        """
        def _update():
            if not self._destroyed:
                version_label = self.root.nametowidget(
                    str(self.root.children[list(self.root.children.keys())[0]])
                )
                # Ищем label версии через проход по детям
                for widget in self.root.winfo_children():
                    for child in widget.winfo_children():
                        if isinstance(child, tk.Label) and "Версия:" in child.cget("text"):
                            child.config(text=f"Версия: {version} | {build_type}")
                            break
        
        self.root.after(0, _update)
    
    def close(self):
        """Закрывает экран загрузки."""
        self._destroyed = True
        try:
            self.root.destroy()
        except:
            pass
    
    def run_initialization(self, init_callback: Callable[[], bool]):
        """
        Запускает процесс инициализации с обновлением UI.
        
        Args:
            init_callback: Функция инициализации, возвращает True при успехе
            
        Returns:
            True если инициализация успешна, False иначе
        """
        success = [True]
        
        def run_in_thread():
            try:
                result = init_callback()
                success[0] = result
            except Exception as e:
                success[0] = False
                self.add_log(f"Критическая ошибка: {str(e)}", "error")
            finally:
                # Закрываем splash screen после завершения
                self.root.after(100, self.close)
        
        thread = threading.Thread(target=run_in_thread, daemon=True)
        thread.start()
        
        return success[0]


def show_splash_and_initialize(init_function: Callable[[], bool]) -> bool:
    """
    Показывает экран загрузки и выполняет инициализацию.
    
    Args:
        init_function: Функция для выполнения инициализации
        
    Returns:
        True если инициализация успешна, False иначе
    """
    splash = SplashScreen()
    
    # Пример последовательности инициализации
    def initialization_sequence():
        steps = [
            ("core_init", "Инициализация ядра..."),
            ("emulator", "Проверка эмулятора..."),
            ("predictor", "Загрузка модели предиктора..."),
            ("detector", "Загрузка модели детектора..."),
            ("classifier", "Инициализация классификатора..."),
            ("scheduler", "Запуск планировщика..."),
            ("gui", "Подготовка интерфейса..."),
            ("logging", "Настройка логирования...")
        ]
        
        for i, (module_key, message) in enumerate(steps):
            splash.update_progress(i + 1, message)
            splash.add_log(f"Шаг {i+1}/8: {message}")
            
            # Симуляция загрузки (в реальности здесь вызов реальных функций)
            time.sleep(0.3)
            
            # Обновляем статус модуля
            splash.update_module_status(module_key, "Загружено", True)
            splash.add_log(f"✓ Модуль {module_key} успешно загружен")
        
        # Вызов реальной функции инициализации
        return init_function()
    
    splash.run_initialization(initialization_sequence)
    
    # Запускаем главный цикл TK
    splash.root.mainloop()
    
    return True


# Пример использования
if __name__ == "__main__":
    def mock_init():
        """Тестовая функция инициализации."""
        print("Выполняется реальная инициализация...")
        time.sleep(1)
        print("Инициализация завершена!")
        return True
    
    show_splash_and_initialize(mock_init)
