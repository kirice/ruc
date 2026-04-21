"""
Emulator Bridge - Обеспечивает запуск/мониторинг процесса эмулятора, захват кадров, 
эмуляцию кликов и нажатий клавиш
"""

import logging
import subprocess
import time
from pathlib import Path
from typing import Optional, Tuple, List, Any
import threading

try:
    import cv2
    import numpy as np
    np_ndarray = np.ndarray if np else None
except ImportError:
    cv2 = None
    np = None
    np_ndarray = None

try:
    from pynput.keyboard import Controller as KeyboardController, Key
    from pynput.mouse import Controller as MouseController
except ImportError:
    KeyboardController = None
    MouseController = None


class EmulatorBridge:
    """Мост для управления эмулятором BlueStacks"""
    
    def __init__(self, config: dict = None):
        self.config = config or {}
        self.logger = logging.getLogger("emulator_bridge")
        
        # Настройки из конфига
        emu_config = self.config.get("emulator", {})
        self.install_path = Path(emu_config.get(
            "install_path", 
            "C:\\Program Files\\BlueStacks_nxt"
        ))
        self.adb_port = emu_config.get("adb_port", 5555)
        self.resolution = tuple(emu_config.get("resolution", (1920, 1080)))
        
        # Состояние
        self._connected = False
        self._process: Optional[subprocess.Popen] = None
        self._window_handle: Optional[int] = None
        
        # Устройства ввода (для локальной эмуляции)
        self._keyboard = KeyboardController() if KeyboardController else None
        self._mouse = MouseController() if MouseController else None
        
        # Сторожевой таймер
        self._watchdog_thread: Optional[threading.Thread] = None
        self._watchdog_running = False
        self._last_frame_time = 0
        self._frame_timeout = emu_config.get("frame_timeout", 5.0)
        
        # ADB путь
        self.adb_path = emu_config.get("adb_path", "adb")
        
        self.logger.info("EmulatorBridge инициализирован")
    
    def check_installation(self) -> bool:
        """Проверка установки эмулятора"""
        self.logger.info(f"Проверка установки в {self.install_path}")
        
        if not self.install_path.exists():
            return False
        
        # Проверка исполняемых файлов
        exe_files = ["HD-Player.exe", "BlueStacks.exe"]
        for exe in exe_files:
            if (self.install_path / exe).exists():
                self.logger.info(f"Найден: {exe}")
                return True
        
        return False
    
    def start_emulator(self) -> bool:
        """Запуск эмулятора"""
        self.logger.info("Запуск эмулятора...")
        
        try:
            player_exe = self.install_path / "HD-Player.exe"
            
            if not player_exe.exists():
                self.logger.error("HD-Player.exe не найден")
                return False
            
            # Запуск процесса
            self._process = subprocess.Popen(
                [str(player_exe)],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )
            
            # Ожидание запуска
            time.sleep(10)
            
            # Проверка подключения через ADB
            if self._check_adb_connection():
                self._connected = True
                self.logger.info("Эмулятор запущен и подключен")
                
                # Запуск сторожевого таймера
                self._start_watchdog()
                
                return True
            else:
                self.logger.warning("Эмулятор запущен, но ADB не отвечает")
                return False
                
        except Exception as e:
            self.logger.error(f"Ошибка запуска эмулятора: {e}", exc_info=True)
            return False
    
    def stop_emulator(self):
        """Остановка эмулятора"""
        self.logger.info("Остановка эмулятора...")
        
        self._watchdog_running = False
        if self._watchdog_thread:
            self._watchdog_thread.join(timeout=2)
        
        if self._process:
            self._process.terminate()
            self._process.wait(timeout=5)
            self._process = None
        
        self._connected = False
        self.logger.info("Эмулятор остановлен")
    
    def _check_adb_connection(self) -> bool:
        """Проверка подключения через ADB"""
        try:
            result = subprocess.run(
                [self.adb_path, "devices"],
                capture_output=True,
                text=True,
                timeout=5
            )
            
            return f"127.0.0.1:{self.adb_port}" in result.stdout or \
                   "emulator" in result.stdout
                   
        except Exception as e:
            self.logger.error(f"Ошибка проверки ADB: {e}")
            return False
    
    def _adb_command(self, cmd: str) -> Optional[str]:
        """Выполнение ADB команды"""
        try:
            full_cmd = f"{self.adb_path} -s 127.0.0.1:{self.adb_port} {cmd}"
            result = subprocess.run(
                full_cmd,
                shell=True,
                capture_output=True,
                text=True,
                timeout=10
            )
            
            if result.returncode == 0:
                return result.stdout
            else:
                self.logger.debug(f"ADB ошибка: {result.stderr}")
                return None
                
        except Exception as e:
            self.logger.error(f"Ошибка ADB команды: {e}")
            return None
    
    def capture_frame(self) -> Optional[Any]:
        """
        Захват кадра из эмулятора
        
        Returns:
            Изображение кадра (BGR) или None при ошибке
        """
        try:
            # Скриншот через ADB
            adb_result = self._adb_command("shell screencap -p")
            
            if adb_result is None:
                # Попытка через window capture (Windows)
                return self._capture_window_frame()
            
            if cv2 and np:
                # Конвертация байтов в изображение
                nparr = np.frombuffer(adb_result.encode('latin1'), np.uint8)
                frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
                
                self._last_frame_time = time.time()
                return frame
            else:
                self.logger.warning("OpenCV не доступен для обработки кадра")
                return None
                
        except Exception as e:
            self.logger.error(f"Ошибка захвата кадра: {e}", exc_info=True)
            return None
    
    def _capture_window_frame(self) -> Optional[Any]:
        """Захват кадра через окно (альтернативный метод)"""
        if not cv2:
            return None
        
        try:
            # Поиск окна эмулятора
            import pyautogui
            screenshot = pyautogui.screenshot()
            frame = cv2.cvtColor(np.array(screenshot), cv2.COLOR_RGB2BGR)
            
            self._last_frame_time = time.time()
            return frame
            
        except Exception as e:
            self.logger.error(f"Ошибка захвата окна: {e}")
            return None
    
    def click(self, x: int, y: int):
        """
        Клик в указанной точке
        
        Args:
            x: Координата X (пиксели)
            y: Координата Y (пиксели)
        """
        try:
            # Через ADB
            result = self._adb_command(f"shell input tap {x} {y}")
            
            if result is None and self._mouse:
                # Fallback через pynput
                from pynput.mouse import Button
                self._mouse.position = (x, y)
                self._mouse.click(Button.left, 1)
            
            self.logger.debug(f"Клик: ({x}, {y})")
            
        except Exception as e:
            self.logger.error(f"Ошибка клика: {e}")
    
    def swipe(self, x1: int, y1: int, x2: int, y2: int, duration: int = 100):
        """
        Свайп от одной точки к другой
        
        Args:
            x1, y1: Начальная точка
            x2, y2: Конечная точка
            duration: Длительность в мс
        """
        try:
            self._adb_command(f"shell input swipe {x1} {y1} {x2} {y2} {duration}")
            self.logger.debug(f"Свайп: ({x1},{y1}) -> ({x2},{y2})")
            
        except Exception as e:
            self.logger.error(f"Ошибка свайпа: {e}")
    
    def press_key(self, key: str):
        """
        Нажатие клавиши
        
        Args:
            key: Название клавиши
        """
        try:
            # Маппинг клавиш для ADB
            key_map = {
                "enter": "KEYCODE_ENTER",
                "back": "KEYCODE_BACK",
                "home": "KEYCODE_HOME",
                "space": "KEYCODE_SPACE",
                "up": "KEYCODE_DPAD_UP",
                "down": "KEYCODE_DPAD_DOWN",
                "left": "KEYCODE_DPAD_LEFT",
                "right": "KEYCODE_DPAD_RIGHT",
            }
            
            adb_key = key_map.get(key.lower(), None)
            
            if adb_key:
                self._adb_command(f"shell input keyevent {adb_key}")
            elif self._keyboard:
                # Fallback через pynput
                self._keyboard.press(key)
                self._keyboard.release(key)
            
            self.logger.debug(f"Нажата клавиша: {key}")
            
        except Exception as e:
            self.logger.error(f"Ошибка нажатия клавиши: {e}")
    
    def get_resolution(self) -> Tuple[int, int]:
        """Получение разрешения экрана эмулятора"""
        try:
            # Попытка получить реальное разрешение через ADB
            output = self._adb_command("shell wm size")
            
            if output:
                import re
                match = re.search(r'(\d+)x(\d+)', output)
                if match:
                    return (int(match.group(1)), int(match.group(2)))
            
            return self.resolution
            
        except Exception as e:
            self.logger.error(f"Ошибка получения разрешения: {e}")
            return self.resolution
    
    def is_connected(self) -> bool:
        """Проверка подключения к эмулятору"""
        if not self._connected:
            return False
        
        # Дополнительная проверка через ADB
        return self._check_adb_connection()
    
    def _start_watchdog(self):
        """Запуск сторожевого таймера"""
        self._watchdog_running = True
        self._watchdog_thread = threading.Thread(
            target=self._watchdog_loop, 
            daemon=True
        )
        self._watchdog_thread.start()
    
    def _watchdog_loop(self):
        """Цикл сторожевого таймера"""
        while self._watchdog_running:
            time.sleep(1)
            
            # Проверка таймаута кадров
            if self._last_frame_time > 0:
                elapsed = time.time() - self._last_frame_time
                if elapsed > self._frame_timeout:
                    self.logger.warning(
                        f"Таймаут кадров ({elapsed:.1f}с). Возможное зависание."
                    )
                    # Можно добавить логику восстановления
    
    def recover(self) -> bool:
        """Попытка восстановления соединения"""
        self.logger.info("Попытка восстановления соединения...")
        
        # Переподключение ADB
        self._adb_command("reconnect")
        time.sleep(2)
        
        if self._check_adb_connection():
            self.logger.info("Соединение восстановлено")
            return True
        else:
            self.logger.error("Не удалось восстановить соединение")
            return False
