"""
Game Bot - Main Application Entry Point

Запускает систему автоматизации игры с управлением через GUI.
Включает экран начальной загрузки перед основным интерфейсом.
"""

import sys
from pathlib import Path

# Добавляем корень проекта в PATH
sys.path.insert(0, str(Path(__file__).parent))

from gui.splash_screen import SplashScreen
from gui.dashboard import Dashboard


def initialize_application(splash=None) -> bool:
    """
    Выполняет инициализацию всех модулей приложения.
    
    Args:
        splash: Опциональный объект splash screen для обновления статуса
        
    Returns:
        True если инициализация успешна, False иначе
    """
    try:
        # Шаг 1: Инициализация ядра
        if splash:
            splash.update_progress(1, "Инициализация ядра...")
            splash.add_log("Загрузка конфигурации...")
        from core.state_machine import StateMachine
        state_machine = StateMachine()
        if splash:
            splash.update_module_status("core_init", "Загружено", True)
            splash.add_log("✓ Ядро системы инициализировано")
        
        # Шаг 2: Проверка эмулятора
        if splash:
            splash.update_progress(2, "Проверка эмулятора...")
            splash.add_log("Поиск установленного BlueStacks...")
        from emulator.bridge import EmulatorBridge
        emulator_bridge = EmulatorBridge()
        if splash:
            splash.update_module_status("emulator", "Готов", True)
            splash.add_log("✓ Эмулятор готов к работе")
        
        # Шаг 3: Загрузка модели предиктора (NN-2)
        if splash:
            splash.update_progress(3, "Загрузка модели предиктора...")
        from neural_networks.predictor import ActionPredictor
        predictor = ActionPredictor()
        if splash:
            splash.update_module_status("predictor", "Загружено", True)
            splash.add_log("✓ Модель предиктора (NN-2) загружена")
        
        # Шаг 4: Загрузка модели детектора (NN-1)
        if splash:
            splash.update_progress(4, "Загрузка модели детектора...")
        from neural_networks.detector import ObjectDetector
        detector = ObjectDetector()
        if splash:
            splash.update_module_status("detector", "Загружено", True)
            splash.add_log("✓ Модель детектора (NN-1) загружена")
        
        # Шаг 5: Инициализация классификатора локаций
        if splash:
            splash.update_progress(5, "Инициализация классификатора...")
        from neural_networks.context_classifier import ContextClassifier
        classifier = ContextClassifier()
        if splash:
            splash.update_module_status("classifier", "Готов", True)
            splash.add_log("✓ Классификатор локаций готов")
        
        # Шаг 6: Запуск планировщика задач
        if splash:
            splash.update_progress(6, "Запуск планировщика...")
        from core.scheduler import TaskScheduler
        scheduler = TaskScheduler()
        if splash:
            splash.update_module_status("scheduler", "Запущен", True)
            splash.add_log("✓ Планировщик задач запущен")
        
        # Шаг 7: Подготовка GUI (без запуска)
        if splash:
            splash.update_progress(7, "Подготовка интерфейса...")
            splash.add_log("Загрузка компонентов GUI...")
        if splash:
            splash.update_module_status("gui", "Готов", True)
            splash.add_log("✓ Интерфейс подготовлен")
        
        # Шаг 8: Настройка логирования
        if splash:
            splash.update_progress(8, "Настройка логирования...")
        if splash:
            splash.update_module_status("logging", "Активно", True)
            splash.add_log("✓ Система логирования активна")
        
        # Сохраняем компоненты в глобальной области видимости для main
        global app_components
        app_components = {
            'state_machine': state_machine,
            'emulator_bridge': emulator_bridge,
            'predictor': predictor,
            'detector': detector,
            'classifier': classifier,
            'scheduler': scheduler
        }
        
        return True
        
    except Exception as e:
        if splash:
            splash.add_log(f"❌ Ошибка инициализации: {str(e)}", "error")
        print(f"❌ Критическая ошибка при инициализации: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """Точка входа приложения с экраном загрузки."""
    print("🤖 Game Bot - Запуск...")
    
    # Показываем экран загрузки и выполняем инициализацию
    splash = SplashScreen()
    
    # Запускаем инициализацию в потоке
    init_success = [True]
    
    def run_initialization():
        try:
            success = initialize_application(splash)
            init_success[0] = success
            
            if success:
                splash.add_log("✅ Все модули успешно загружены!")
                splash.update_progress(8, "Готово к запуску")
            else:
                splash.add_log("❌ Ошибка инициализации", "error")
                
        except Exception as e:
            init_success[0] = False
            splash.add_log(f"❌ Критическая ошибка: {str(e)}", "error")
        finally:
            # Закрываем splash screen через небольшую паузу
            splash.root.after(800, splash.close)
    
    import threading
    init_thread = threading.Thread(target=run_initialization, daemon=True)
    init_thread.start()
    
    # Запускаем цикл splash screen
    splash.root.mainloop()
    
    # Проверяем результат инициализации
    if not init_success[0]:
        print("❌ Запуск отменён из-за ошибки инициализации")
        sys.exit(1)
    
    # Создаём и запускаем главный интерфейс с инициализированными компонентами
    try:
        app = Dashboard(
            scheduler=app_components['scheduler'],
            state_machine=app_components['state_machine']
        )
        app.start()
    except Exception as e:
        print(f"❌ Ошибка при запуске GUI: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    
    print("👋 Game Bot - Завершение работы")


if __name__ == "__main__":
    main()
