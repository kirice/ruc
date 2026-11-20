"""
Менеджер BlueStacks - установка, настройка и управление эмулятором
"""

import logging
import subprocess
import shutil
from pathlib import Path
from typing import Optional, Tuple


class BlueStacksManager:
    """Управление эмулятором BlueStacks"""
    
    def __init__(self, config: dict):
        self.config = config
        self.logger = logging.getLogger("bluestacks_manager")
        
        # Пути и настройки из конфига
        self.install_path = Path(config.get("bluestacks", {}).get(
            "install_path", 
            "C:\\Program Files\\BlueStacks_nxt"
        ))
        self.adb_port = config.get("bluestacks", {}).get("adb_port", 5555)
        
        # Состояние подключения
        self._connected = False
        self._process = None
    
    def check_installation(self) -> bool:
        """
        Проверка установки BlueStacks
        
        Returns:
            True если BlueStacks установлен, иначе False
        """
        self.logger.info(f"Проверка установки BlueStacks в {self.install_path}")
        
        if not self.install_path.exists():
            return False
        
        # Проверка основных исполняемых файлов
        exe_files = ["HD-Player.exe", "BlueStacks.exe"]
        for exe in exe_files:
            if (self.install_path / exe).exists():
                return True
        
        return False
    
    def install(self, installer_url: str = None) -> bool:
        """
        Установка BlueStacks
        
        Args:
            installer_url: URL для скачивания установщика (опционально)
            
        Returns:
            True если установка успешна, иначе False
        """
        self.logger.info("Запуск установки BlueStacks...")
        
        try:
            # Если URL не указан, используем официальный
            if not installer_url:
                installer_url = "https://cloud.bluestacks.com/api/vinyl/get_installer?channel=main_bs5&lang=ru"
            
            # Скачивание установщика
            import requests
            
            temp_dir = Path("temp")
            temp_dir.mkdir(exist_ok=True)
            installer_path = temp_dir / "BlueStacksInstaller.exe"
            
            self.logger.info(f"Скачивание установщика с {installer_url}")
            response = requests.get(installer_url, stream=True)
            response.raise_for_status()
            
            with open(installer_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)
            
            # Тихая установка
            self.logger.info("Запуск тихой установки...")
            result = subprocess.run(
                [str(installer_path), "--silent"],
                capture_output=True,
                text=True
            )
            
            if result.returncode == 0:
                self.logger.info("BlueStacks успешно установлен")
                return True
            else:
                self.logger.error(f"Ошибка установки: {result.stderr}")
                return False
                
        except Exception as e:
            self.logger.error(f"Ошибка при установке: {e}", exc_info=True)
            return False
    
    def configure(self) -> bool:
        """
        Настройка параметров эмулятора
        
        Returns:
            True если настройка успешна, иначе False
        """
        self.logger.info("Настройка BlueStacks...")
        
        try:
            # Путь к конфигурационному файлу BlueStacks
            config_file = Path(
                "C:\\ProgramData\\BlueStacks_nxt\\bluestacks.conf"
            )
            
            if not config_file.exists():
                self.logger.warning("Файл конфигурации BlueStacks не найден")
                return False
            
            # Чтение текущей конфигурации
            with open(config_file, 'r', encoding='utf-8') as f:
                lines = f.readlines()
            
            # Обновление параметров
            bs_config = self.config.get("bluestacks", {})
            updates = {
                "memory": f"memory={bs_config.get('memory', 4096)}",
                "cpu_cores": f"cpu_cores={bs_config.get('cpu_cores', 4)}",
                "resolution_width": f"resolution_width={bs_config.get('resolution', {}).get('width', 1920)}",
                "resolution_height": f"resolution_height={bs_config.get('resolution', {}).get('height', 1080)}",
                "root": f"root={1 if bs_config.get('enable_root', True) else 0}",
            }
            
            # Запись обновленных параметров
            updated = False
            for i, line in enumerate(lines):
                for key, value in updates.items():
                    if line.startswith(key + "="):
                        lines[i] = value + "\n"
                        updated = True
            
            if updated:
                with open(config_file, 'w', encoding='utf-8') as f:
                    f.writelines(lines)
                self.logger.info("Конфигурация BlueStacks обновлена")
            
            return True
            
        except Exception as e:
            self.logger.error(f"Ошибка настройки: {e}", exc_info=True)
            return False
    
    def start_emulator(self) -> bool:
        """
        Запуск эмулятора
        
        Returns:
            True если запуск успешен, иначе False
        """
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
            
            # Ожидание запуска (можно добавить проверку через ADB)
            import time
            time.sleep(10)
            
            self._connected = True
            self.logger.info("Эмулятор запущен")
            return True
            
        except Exception as e:
            self.logger.error(f"Ошибка запуска эмулятора: {e}", exc_info=True)
            return False
    
    def launch_game(self, package_name: str = None) -> bool:
        """
        Запуск игры в эмуляторе
        
        Args:
            package_name: Имя пакета игры (опционально)
            
        Returns:
            True если запуск успешен, иначе False
        """
        self.logger.info("Запуск игры...")
        
        try:
            # Использование ADB для запуска игры
            adb = self._get_adb_command()
            
            if not package_name:
                # Попытка определить пакет игры (можно настроить)
                package_name = "com.rako.online"  # Пример
            
            cmd = f"{adb} shell monkey -p {package_name} -c android.intent.category.LAUNCHER 1"
            result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
            
            if result.returncode == 0:
                self.logger.info(f"Игра {package_name} запущена")
                return True
            else:
                self.logger.warning(f"Не удалось запустить игру: {result.stderr}")
                return False
                
        except Exception as e:
            self.logger.error(f"Ошибка запуска игры: {e}", exc_info=True)
            return False
    
    def is_connected(self) -> bool:
        """
        Проверка подключения к эмулятору
        
        Returns:
            True если подключено, иначе False
        """
        if not self._connected:
            return False
        
        try:
            adb = self._get_adb_command()
            result = subprocess.run(
                f"{adb} devices",
                shell=True,
                capture_output=True,
                text=True
            )
            
            return "emulator" in result.stdout or "127.0.0.1" in result.stdout
            
        except Exception:
            return False
    
    def take_screenshot(self, save_path: str = None) -> Optional[bytes]:
        """
        Скриншот экрана эмулятора
        
        Args:
            save_path: Путь для сохранения (опционально)
            
        Returns:
            Байты изображения или None при ошибке
        """
        try:
            adb = self._get_adb_command()
            
            # Скриншот через ADB
            cmd = f"{adb} shell screencap -p"
            result = subprocess.run(cmd, shell=True, capture_output=True)
            
            if result.returncode == 0:
                image_data = result.stdout
                
                if save_path:
                    with open(save_path, 'wb') as f:
                        f.write(image_data)
                
                return image_data
            
            return None
            
        except Exception as e:
            self.logger.error(f"Ошибка скриншота: {e}", exc_info=True)
            return None
    
    def click(self, x: int, y: int):
        """
        Клик в указанной точке
        
        Args:
            x: Координата X
            y: Координата Y
        """
        try:
            adb = self._get_adb_command()
            cmd = f"{adb} shell input tap {x} {y}"
            subprocess.run(cmd, shell=True, capture_output=True)
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
            adb = self._get_adb_command()
            cmd = f"{adb} shell input swipe {x1} {y1} {x2} {y2} {duration}"
            subprocess.run(cmd, shell=True, capture_output=True)
        except Exception as e:
            self.logger.error(f"Ошибка свайпа: {e}")
    
    def _get_adb_command(self) -> str:
        """Получение команды ADB с портом"""
        return f"adb connect 127.0.0.1:{self.adb_port} && adb -s 127.0.0.1:{self.adb_port}"
    
    def stop(self):
        """Остановка эмулятора"""
        if self._process:
            self._process.terminate()
            self._connected = False
            self.logger.info("Эмулятор остановлен")
