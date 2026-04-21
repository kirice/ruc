"""
Главный файл запуска приложения-бота
"""

import logging
import sys
from pathlib import Path

# Настройка логирования
def setup_logging():
    """Настройка системы логирования"""
    log_dir = Path("logs")
    log_dir.mkdir(parents=True, exist_ok=True)
    
    # Формат логов
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    # Системный лог
    system_handler = logging.FileHandler(log_dir / "system.log", encoding='utf-8')
    system_handler.setFormatter(formatter)
    system_handler.setLevel(logging.INFO)
    
    # Консольный вывод
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    console_handler.setLevel(logging.INFO)
    
    # Корневой логгер
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)
    root_logger.addHandler(system_handler)
    root_logger.addHandler(console_handler)
    
    return logging.getLogger("main")


def main():
    """Точка входа приложения"""
    logger = setup_logging()
    logger.info("=" * 50)
    logger.info("Запуск приложения-бота для автоматизации игры")
    logger.info("=" * 50)
    
    try:
        # Импорт основных компонентов
        from core.state_machine import StateMachine, BotState
        from core.scheduler import Scheduler, CommandPriority
        from core.action_loop import ActionLoop
        from emulator.bridge import EmulatorBridge
        from neural_networks.predictor import Predictor
        from neural_networks.detector import Detector
        from neural_networks.context_classifier import ContextClassifier
        from gui.dashboard import Dashboard, TrainerOverlay
        from gui.consoles import ConsolesManager, CommandFilter, ConsoleType
        
        logger.info("Все модули успешно импортированы")
        
        # Базовая конфигурация
        config = {
            "paths": {
                "bots_config_dir": "config/bots",
                "maps_config_dir": "config/maps"
            },
            "loop": {
                "fps_limit": 30,
                "confidence_threshold": 0.7,
                "action_delay": 0.1,
                "stabilization_wait": 0.2,
                "max_low_confidence": 5
            },
            "gui": {
                "enabled": False  # Отключаем GUI для headless режима
            }
        }
        
        # Инициализация компонентов
        logger.info("Инициализация компонентов...")
        
        # State Machine
        state_machine = StateMachine(config)
        state_machine.create_profile(bot_id="bot_1", name="Test Bot")
        logger.info("State Machine инициализирован")
        
        # Scheduler
        scheduler = Scheduler(config)
        scheduler.start()
        logger.info("Scheduler запущен")
        
        # Emulator Bridge (заглушка без реального эмулятора)
        emulator = EmulatorBridge(config)
        logger.info("Emulator Bridge инициализирован")
        
        # Neural Networks
        predictor = Predictor(config)
        detector = Detector(config)
        classifier = ContextClassifier(config)
        logger.info("Нейросети инициализированы")
        
        # Dashboard
        dashboard = Dashboard(scheduler, state_machine, config)
        dashboard.start()
        logger.info("Dashboard инициализирован")
        
        # Consoles Manager
        consoles = ConsolesManager(scheduler, config)
        logger.info("Consoles Manager инициализирован")
        
        # Тестовая команда
        logger.info("Отправка тестовой команды...")
        consoles.add_command("status", ConsoleType.SYSTEM, source="test")
        consoles.add_command("move forward", ConsoleType.FLOOD, source="test")
        
        # Статистика
        import time
        time.sleep(1)
        
        logger.info("Статистика очередей:")
        stats = consoles.get_queue_stats()
        for key, value in stats.items():
            logger.info(f"  {key}: {value}")
        
        logger.info("Приложение успешно инициализировано и готово к работе!")
        logger.info("Для остановки нажмите Ctrl+C")
        
        # Основной цикл (упрощённый)
        try:
            while True:
                time.sleep(1)
                
                # Проверка состояния
                if not scheduler._running:
                    logger.warning("Scheduler остановлен")
                    break
                    
        except KeyboardInterrupt:
            logger.info("Получен сигнал остановки (Ctrl+C)")
        
        # Остановка
        logger.info("Остановка приложения...")
        scheduler.stop()
        dashboard.stop()
        
        logger.info("Приложение остановлено")
        
    except Exception as e:
        logger.error(f"Критическая ошибка: {e}", exc_info=True)
        return 1
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
