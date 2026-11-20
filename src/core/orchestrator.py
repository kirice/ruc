"""
Оркестратор - центральное ядро системы
Координирует все компоненты: BlueStacks, бот, скриншотер, GUI
"""

import logging
import sys
from pathlib import Path
from typing import Optional

# Добавляем корень проекта в path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.bluestacks.manager import BlueStacksManager
from src.bot.core import BotCore
from src.screenshotter.capture import Screenshotter
from src.gui.main_window import MainWindow
from configs.config_loader import ConfigLoader


class Orchestrator:
    """Центральный оркестратор системы"""
    
    def __init__(self, config_path: str = "configs/config.yaml"):
        self.config = ConfigLoader.load(config_path)
        self.logger = self._setup_logging()
        
        # Инициализация компонентов
        self.bluestacks_manager: Optional[BlueStacksManager] = None
        self.bot_core: Optional[BotCore] = None
        self.screenshotter: Optional[Screenshotter] = None
        self.gui: Optional[MainWindow] = None
        
        # Состояние системы
        self.is_running = False
        self.components_initialized = False
        
        self.logger.info("Оркестратор инициализирован")
    
    def _setup_logging(self) -> logging.Logger:
        """Настройка логирования"""
        logger = logging.getLogger("orchestrator")
        logger.setLevel(logging.INFO)
        
        # Консольный обработчик
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.INFO)
        
        # Файловый обработчик
        log_path = Path(self.config.get("paths", {}).get("logs_path", "logs/bot.log"))
        log_path.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(log_path, encoding="utf-8")
        file_handler.setLevel(logging.DEBUG)
        
        # Форматтер
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        console_handler.setFormatter(formatter)
        file_handler.setFormatter(formatter)
        
        logger.addHandler(console_handler)
        logger.addHandler(file_handler)
        
        return logger
    
    def initialize_components(self) -> bool:
        """Инициализация всех компонентов системы"""
        try:
            self.logger.info("Инициализация компонентов...")
            
            # 1. BlueStacks Manager
            self.bluestacks_manager = BlueStacksManager(self.config)
            if not self.bluestacks_manager.check_installation():
                self.logger.warning("BlueStacks не найден. Запуск установки...")
                if not self.bluestacks_manager.install():
                    self.logger.error("Не удалось установить BlueStacks")
                    return False
            
            # Настройка эмулятора
            if not self.bluestacks_manager.configure():
                self.logger.error("Не удалось настроить BlueStacks")
                return False
            
            # 2. Бот
            self.bot_core = BotCore(self.config, self.bluestacks_manager)
            
            # 3. Скриншотер
            self.screenshotter = Screenshotter(self.config, self.bluestacks_manager)
            
            # 4. GUI (опционально, если нужен интерфейс)
            # self.gui = MainWindow(self.config, self)
            
            self.components_initialized = True
            self.logger.info("Все компоненты успешно инициализированы")
            return True
            
        except Exception as e:
            self.logger.error(f"Ошибка инициализации: {e}", exc_info=True)
            return False
    
    def start(self) -> bool:
        """Запуск системы"""
        if not self.components_initialized:
            if not self.initialize_components():
                return False
        
        try:
            self.logger.info("Запуск системы...")
            self.is_running = True
            
            # Запуск эмулятора и игры
            if not self.bluestacks_manager.start_emulator():
                self.logger.error("Не удалось запустить эмулятор")
                return False
            
            if not self.bluestacks_manager.launch_game():
                self.logger.error("Не удалось запустить игру")
                return False
            
            # Запуск бота
            self.bot_core.start()
            
            # Запуск скриншотера (если нужен)
            # self.screenshotter.start_capture()
            
            self.logger.info("Система запущена")
            return True
            
        except Exception as e:
            self.logger.error(f"Ошибка запуска: {e}", exc_info=True)
            self.is_running = False
            return False
    
    def stop(self):
        """Остановка системы"""
        try:
            self.logger.info("Остановка системы...")
            self.is_running = False
            
            # Остановка компонентов в обратном порядке
            if self.bot_core:
                self.bot_core.stop()
            
            if self.screenshotter:
                self.screenshotter.stop_capture()
            
            self.logger.info("Система остановлена")
            
        except Exception as e:
            self.logger.error(f"Ошибка остановки: {e}", exc_info=True)
    
    def get_status(self) -> dict:
        """Получение статуса системы"""
        return {
            "is_running": self.is_running,
            "components_initialized": self.components_initialized,
            "bluestacks_connected": self.bluestacks_manager.is_connected() if self.bluestacks_manager else False,
            "bot_active": self.bot_core.is_active if self.bot_core else False,
        }
    
    def run_gui(self):
        """Запуск графического интерфейса"""
        if not self.components_initialized:
            self.initialize_components()
        
        from PyQt5.QtWidgets import QApplication
        
        app = QApplication(sys.argv)
        window = MainWindow(self.config, self)
        window.show()
        sys.exit(app.exec_())


def main():
    """Точка входа"""
    orchestrator = Orchestrator()
    
    # Для работы с GUI раскомментируйте:
    # orchestrator.run_gui()
    
    # Для консольного режима:
    if orchestrator.start():
        try:
            while orchestrator.is_running:
                pass
        except KeyboardInterrupt:
            orchestrator.stop()


if __name__ == "__main__":
    main()
