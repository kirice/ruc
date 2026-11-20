"""
Action Loop - Координирует непрерывный цикл: захват кадра → инференс → валидация → эмуляция ввода → логирование
"""

import logging
import time
import threading
from pathlib import Path
from typing import Optional, Dict, Any, Tuple
import numpy as np

try:
    import cv2
except ImportError:
    cv2 = None


class ActionLoop:
    """Основной цикл восприятия-действия бота"""
    
    def __init__(self, emulator_bridge, predictor, detector=None, config: dict = None):
        self.emulator = emulator_bridge
        self.predictor = predictor
        self.detector = detector
        self.config = config or {}
        
        self.logger = logging.getLogger("action_loop")
        
        # Настройки цикла
        loop_config = self.config.get("loop", {})
        self.fps_limit = loop_config.get("fps_limit", 30)
        self.confidence_threshold = loop_config.get("confidence_threshold", 0.7)
        self.action_delay = loop_config.get("action_delay", 0.1)
        self.stabilization_wait = loop_config.get("stabilization_wait", 0.2)
        
        # Состояние
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._frame_count = 0
        self._last_action_time = 0
        self._low_confidence_count = 0
        self._max_low_confidence = loop_config.get("max_low_confidence", 5)
        
        # Метрики
        self.metrics = {
            "fps": 0.0,
            "last_prediction": None,
            "last_action": None,
            "low_confidence_streak": 0
        }
        
        # Callbacks для GUI
        self.on_frame_captured = None
        self.on_prediction_made = None
        self.on_action_executed = None
        
        self.logger.info("ActionLoop инициализирован")
    
    def start(self):
        """Запуск цикла в отдельном потоке"""
        if self._running:
            return
        
        self._running = True
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()
        self.logger.info("ActionLoop запущен")
    
    def stop(self):
        """Остановка цикла"""
        self._running = False
        if self._thread:
            self._thread.join(timeout=5)
        self.logger.info("ActionLoop остановлен")
    
    def _run_loop(self):
        """Основной цикл восприятия-действия"""
        last_time = time.time()
        
        while self._running:
            try:
                cycle_start = time.time()
                
                # 1. Захват кадра
                frame = self.emulator.capture_frame()
                if frame is None:
                    self.logger.warning("Не удалось захватить кадр")
                    time.sleep(0.1)
                    continue
                
                self._frame_count += 1
                
                # Callback для GUI
                if self.on_frame_captured:
                    self.on_frame_captured(frame)
                
                # 2. Нормализация
                normalized_frame = self._normalize_frame(frame)
                
                # 3. Инференс предиктора (NN-2)
                prediction = self.predictor.predict(normalized_frame)
                
                if prediction:
                    x, y, confidence = prediction
                    
                    # Обновление метрик
                    self.metrics["last_prediction"] = {
                        "x": x,
                        "y": y,
                        "confidence": confidence
                    }
                    
                    # Callback для GUI
                    if self.on_prediction_made:
                        self.on_prediction_made(x, y, confidence)
                    
                    # 4. Фильтрация по уверенности
                    if confidence < self.confidence_threshold:
                        self._low_confidence_count += 1
                        self.metrics["low_confidence_streak"] = self._low_confidence_count
                        
                        if self._low_confidence_count >= self._max_low_confidence:
                            self.logger.warning(
                                f"Низкая уверенность ({self._low_confidence_count} раз подряд). "
                                "Приостановка цикла."
                            )
                            self._handle_low_confidence()
                            continue
                    else:
                        self._low_confidence_count = 0
                        self.metrics["low_confidence_streak"] = 0
                    
                    # 5. Проверка зоны клика
                    if self._is_valid_click_zone(x, y):
                        # 6. Выполнение действия
                        current_time = time.time()
                        if current_time - self._last_action_time >= self.action_delay:
                            self._execute_action(x, y)
                            self._last_action_time = current_time
                            
                            # 7. Стабилизация
                            time.sleep(self.stabilization_wait)
                    else:
                        self.logger.debug(f"Координаты ({x}, {y}) вне допустимой зоны")
                
                # Логирование предсказания
                self._log_prediction(prediction)
                
                # Контроль FPS
                cycle_time = time.time() - cycle_start
                target_frame_time = 1.0 / self.fps_limit
                if cycle_time < target_frame_time:
                    sleep_time = target_frame_time - cycle_time
                    time.sleep(sleep_time)
                
                # Обновление FPS метрики
                current_time = time.time()
                elapsed = current_time - last_time
                if elapsed >= 1.0:
                    self.metrics["fps"] = self._frame_count / elapsed
                    self._frame_count = 0
                    last_time = current_time
                
            except Exception as e:
                self.logger.error(f"Ошибка в цикле: {e}", exc_info=True)
                time.sleep(0.5)
    
    def _normalize_frame(self, frame: np.ndarray) -> np.ndarray:
        """Нормализация кадра для модели"""
        if frame is None:
            return None
        
        # Приведение к фиксированному разрешению
        target_size = self.config.get("model", {}).get("input_size", (640, 640))
        
        if cv2:
            normalized = cv2.resize(frame, target_size)
            # BGR -> RGB
            normalized = cv2.cvtColor(normalized, cv2.COLOR_BGR2RGB)
            # Нормализация значений пикселей
            normalized = normalized.astype(np.float32) / 255.0
        else:
            # Fallback без OpenCV
            from PIL import Image
            img = Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
            img = img.resize(target_size)
            normalized = np.array(img, dtype=np.float32) / 255.0
        
        return normalized
    
    def _is_valid_click_zone(self, x: float, y: float) -> bool:
        """Проверка попадания координат в допустимую зону клика"""
        # Получаем зону исключения из конфига карты
        exclude_zones = self.config.get("map", {}).get("click_exclude_zones", [])
        
        for zone in exclude_zones:
            x_min, y_min, x_max, y_max = zone
            if x_min <= x <= x_max and y_min <= y <= y_max:
                return False
        
        # Проверка границ экрана (нормализованные координаты от -1 до 1)
        if abs(x) > 1.0 or abs(y) > 1.0:
            return False
        
        return True
    
    def _execute_action(self, x: float, y: float):
        """Выполнение действия (клик)"""
        try:
            # Масштабирование координат под разрешение окна
            screen_width, screen_height = self.emulator.get_resolution()
            
            # Конвертация из нормализованных координат (-1..1) в пиксели
            pixel_x = int((x + 1) / 2 * screen_width)
            pixel_y = int((y + 1) / 2 * screen_height)
            
            # Эмуляция клика
            self.emulator.click(pixel_x, pixel_y)
            
            # Обновление метрик
            self.metrics["last_action"] = {
                "x": pixel_x,
                "y": pixel_y,
                "timestamp": time.time()
            }
            
            # Callback для GUI
            if self.on_action_executed:
                self.on_action_executed(pixel_x, pixel_y)
            
            self.logger.debug(f"Клик выполнен: ({pixel_x}, {pixel_y})")
            
        except Exception as e:
            self.logger.error(f"Ошибка выполнения действия: {e}")
    
    def _handle_low_confidence(self):
        """Обработка серии низкой уверенности"""
        # Микро-сдвиг камеры или пауза
        self.logger.info("Попытка стабилизации визуального ряда...")
        time.sleep(0.5)
    
    def _log_prediction(self, prediction: Optional[Tuple[float, float, float]]):
        """Логирование предсказания"""
        if prediction is None:
            return
        
        x, y, confidence = prediction
        
        # Логирование в predictions.log
        log_path = Path("logs/predictions.log")
        log_path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(log_path, "a", encoding="utf-8") as f:
            timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
            f.write(f"{timestamp} - Prediction: x={x:.4f}, y={y:.4f}, conf={confidence:.4f}\n")
    
    def get_metrics(self) -> Dict[str, Any]:
        """Получение текущих метрик цикла"""
        return self.metrics.copy()
    
    def is_running(self) -> bool:
        """Проверка статуса цикла"""
        return self._running
