"""
Основной модуль бота - логика игры, обнаружение мобов, атака
"""

import logging
import time
from pathlib import Path
from typing import List, Dict, Optional, Tuple
import numpy as np

try:
    import cv2
    import onnxruntime as ort
except ImportError:
    cv2 = None
    ort = None


class BotCore:
    """Ядро бота для автоматизации игры"""
    
    def __init__(self, config: dict, bluestacks_manager):
        self.config = config
        self.bluestacks = bluestacks_manager
        self.logger = logging.getLogger("bot_core")
        
        # Настройки из конфига
        bot_config = config.get("bot", {})
        self.detection_threshold = bot_config.get("detection_threshold", 0.6)
        self.action_delay = bot_config.get("action_delay", 100) / 1000.0
        self.attack_delay = bot_config.get("attack_delay", 200) / 1000.0
        self.max_attack_distance = bot_config.get("max_attack_distance", 300)
        
        # Состояние
        self.is_active = False
        self._running = False
        
        # Модель обнаружения
        self.model_session = None
        self.input_name = None
        self.output_names = None
        
        # Загрузка модели
        self._load_model()
    
    def _load_model(self):
        """Загрузка ONNX модели для обнаружения мобов"""
        model_path = self.config.get("paths", {}).get(
            "model_path", 
            "models/model.onnx"
        )
        
        if not Path(model_path).exists():
            self.logger.warning(f"Модель не найдена: {model_path}")
            return
        
        try:
            self.model_session = ort.InferenceSession(str(model_path))
            self.input_name = self.model_session.get_inputs()[0].name
            self.output_names = [o.name for o in self.model_session.get_outputs()]
            self.logger.info(f"Модель загружена: {model_path}")
        except Exception as e:
            self.logger.error(f"Ошибка загрузки модели: {e}")
    
    def start(self):
        """Запуск бота"""
        if self.is_active:
            return
        
        self._running = True
        self.is_active = True
        self.logger.info("Бот запущен")
        
        # Запуск основного цикла в отдельном потоке
        import threading
        thread = threading.Thread(target=self._main_loop, daemon=True)
        thread.start()
    
    def stop(self):
        """Остановка бота"""
        self._running = False
        self.is_active = False
        self.logger.info("Бот остановлен")
    
    def _main_loop(self):
        """Основной цикл бота"""
        while self._running:
            try:
                # 1. Получение скриншота
                screenshot = self.bluestacks.take_screenshot()
                if screenshot is None:
                    time.sleep(1)
                    continue
                
                # Конвертация в изображение OpenCV
                nparr = np.frombuffer(screenshot, np.uint8)
                frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
                
                # 2. Обнаружение мобов
                mobs = self.detect_mobs(frame)
                
                if mobs:
                    self.logger.info(f"Обнаружено мобов: {len(mobs)}")
                    
                    # 3. Выбор цели и атака
                    target = self._select_target(mobs)
                    if target:
                        self._attack(target)
                else:
                    self.logger.debug("Мобы не обнаружены")
                
                time.sleep(self.action_delay)
                
            except Exception as e:
                self.logger.error(f"Ошибка в цикле: {e}", exc_info=True)
                time.sleep(1)
    
    def detect_mobs(self, frame: np.ndarray) -> List[Dict]:
        """
        Обнаружение мобов на изображении
        
        Args:
            frame: Изображение кадра
            
        Returns:
            Список обнаруженных мобов с координатами
        """
        if self.model_session is None:
            return []
        
        try:
            # Предобработка изображения
            input_image = self._preprocess_image(frame)
            
            # Инференс модели
            outputs = self.model_session.run(
                self.output_names,
                {self.input_name: input_image}
            )
            
            # Постобработка результатов
            mobs = self._postprocess_results(outputs, frame.shape)
            
            return mobs
            
        except Exception as e:
            self.logger.error(f"Ошибка обнаружения: {e}")
            return []
    
    def _preprocess_image(self, frame: np.ndarray) -> np.ndarray:
        """Предобработка изображения для модели"""
        # Изменение размера
        resized = cv2.resize(frame, (640, 640))
        
        # Конвертация BGR -> RGB
        rgb = cv2.cvtColor(resized, cv2.COLOR_BGR2RGB)
        
        # Нормализация
        normalized = rgb.astype(np.float32) / 255.0
        
        # Транспонирование (HWC -> CHW)
        transposed = np.transpose(normalized, (2, 0, 1))
        
        # Добавление батч-измерения
        batched = np.expand_dims(transposed, axis=0)
        
        return batched
    
    def _postprocess_results(self, outputs: List[np.ndarray], 
                              original_shape: Tuple) -> List[Dict]:
        """Постобработка результатов модели"""
        mobs = []
        
        # Пример обработки для YOLO-like модели
        output = outputs[0][0]  # Первый выход, убираем батч
        
        for detection in output:
            confidence = float(detection[4])
            
            if confidence >= self.detection_threshold:
                # Координаты bounding box
                x_center, y_center, width, height = detection[:4]
                
                # Конвертация в пиксели оригинального изображения
                scale_x = original_shape[1] / 640
                scale_y = original_shape[0] / 640
                
                x1 = int((x_center - width / 2) * scale_x)
                y1 = int((y_center - height / 2) * scale_y)
                x2 = int((x_center + width / 2) * scale_x)
                y2 = int((y_center + height / 2) * scale_y)
                
                mobs.append({
                    "confidence": confidence,
                    "bbox": (x1, y1, x2, y2),
                    "center": ((x1 + x2) // 2, (y1 + y2) // 2)
                })
        
        return mobs
    
    def _select_target(self, mobs: List[Dict]) -> Optional[Dict]:
        """
        Выбор цели для атаки
        
        Args:
            mobs: Список обнаруженных мобов
            
        Returns:
            Выбранный моб или None
        """
        if not mobs:
            return None
        
        # Выбираем ближайшего к центру экрана
        screen_center = (960, 540)  # Для 1920x1080
        
        min_distance = float('inf')
        target = None
        
        for mob in mobs:
            center = mob["center"]
            distance = ((center[0] - screen_center[0]) ** 2 + 
                       (center[1] - screen_center[1]) ** 2) ** 0.5
            
            if distance < min_distance:
                min_distance = distance
                target = mob
        
        return target
    
    def _attack(self, target: Dict):
        """
        Атака цели
        
        Args:
            target: Цель для атаки
        """
        center = target["center"]
        
        self.logger.info(f"Атака цели в {center}")
        
        # Клик по цели
        self.bluestacks.click(center[0], center[1])
        
        # Использование навыков (опционально)
        time.sleep(self.attack_delay / 2)
        self._use_skills()
        
        time.sleep(self.attack_delay)
    
    def _use_skills(self):
        """Использование боевых навыков"""
        skills = self.config.get("bot", {}).get("skills", [])
        
        # Эмуляция нажатий клавиш для навыков
        # Реализация зависит от конкретной игры
        pass
    
    def get_frame_with_detections(self, frame: np.ndarray, 
                                   mobs: List[Dict]) -> np.ndarray:
        """
        Отрисовка обнаруженных мобов на кадре
        
        Args:
            frame: Исходное изображение
            mobs: Список обнаруженных мобов
            
        Returns:
            Изображение с отрисованными bounding box
        """
        result = frame.copy()
        
        for mob in mobs:
            x1, y1, x2, y2 = mob["bbox"]
            confidence = mob["confidence"]
            
            # Рисуем прямоугольник
            color = (0, 255, 0)  # Зеленый
            cv2.rectangle(result, (x1, y1), (x2, y2), color, 2)
            
            # Подпись с уверенностью
            label = f"Mob: {confidence:.2f}"
            cv2.putText(result, label, (x1, y1 - 10),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 2)
        
        return result
