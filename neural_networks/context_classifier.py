"""
Context Classifier - Лёгкий классификатор локации по визуальному паттерну фона/интерфейса.
Выбирает активную модель предиктора и подгружает конфигурацию карты.
"""

import logging
from pathlib import Path
from typing import Optional, Dict, Any, Tuple
import numpy as np

try:
    import onnxruntime as ort
except ImportError:
    ort = None


class ContextClassifier:
    """
    Классификатор контекста (локации)
    
    Вход: Кадр изображения
    Выход: Идентификатор карты + уверенность классификации
    """
    
    def __init__(self, config: dict = None):
        self.config = config or {}
        self.logger = logging.getLogger("context_classifier")
        
        # Настройки
        model_config = self.config.get("classifier", {})
        self.input_size = tuple(model_config.get("input_size", (224, 224)))
        self.confidence_threshold = model_config.get("confidence_threshold", 0.6)
        self.default_model_path = model_config.get("default_model_path", "models/classifier_default.onnx")
        
        # Маппинг классов (индекс -> ID карты)
        self.class_to_map = model_config.get("class_to_map", {
            0: "map1",
            1: "map2",
            2: "map3"
        })
        
        # Конфигурации карт
        self.maps_config_dir = Path(self.config.get("paths", {}).get(
            "maps_config_dir", "config/maps"
        ))
        
        # Состояние
        self._session: Optional[ort.InferenceSession] = None
        self._input_name: Optional[str] = None
        self._output_names: Optional[list] = None
        self._current_map_id: str = ""
        self._current_confidence: float = 0.0
        self._last_classification_time: float = 0
        
        # Кэш последних классификаций для стабильности
        self._classification_history: list = []
        self._history_size = model_config.get("history_size", 5)
        
        # Метрики
        self.metrics = {
            "classification_count": 0,
            "map_changes": 0,
            "avg_inference_time_ms": 0.0
        }
        
        self.logger.info("ContextClassifier инициализирован")
    
    def load_model(self, model_path: str) -> bool:
        """Загрузка модели классификатора"""
        try:
            if ort is None:
                self.logger.error("onnxruntime не установлен")
                return False
            
            path = Path(model_path)
            if not path.exists():
                self.logger.warning(f"Модель не найдена: {model_path}")
                default_path = Path(self.default_model_path)
                if default_path.exists():
                    model_path = str(default_path)
                else:
                    return False
            
            providers = ['CUDAExecutionProvider', 'CPUExecutionProvider']
            self._session = ort.InferenceSession(model_path, providers=providers)
            
            self._input_name = self._session.get_inputs()[0].name
            self._output_names = [o.name for o in self._session.get_outputs()]
            
            self.logger.info(f"Classifier модель загружена: {model_path}")
            return True
            
        except Exception as e:
            self.logger.error(f"Ошибка загрузки классификатора: {e}", exc_info=True)
            return False
    
    def classify(self, frame: np.ndarray, force: bool = False) -> Optional[str]:
        """
        Классификация текущей локации
        
        Args:
            frame: Кадр изображения
            force: Принудительная классификация без учёта кэша
            
        Returns:
            ID карты или None при ошибке
        """
        if self._session is None:
            return None
        
        if frame is None:
            return None
        
        # Не классифицируем слишком часто (раз в 2 секунды)
        import time
        current_time = time.time()
        if not force and current_time - self._last_classification_time < 2.0:
            return self._current_map_id
        
        try:
            start_time = time.time()
            
            # Предобработка
            input_tensor = self._prepare_input(frame)
            
            # Инференс
            outputs = self._session.run(self._output_names, {self._input_name: input_tensor})
            
            # Обработка результата
            class_idx, confidence = self._process_output(outputs)
            
            # Получение ID карты
            map_id = self.class_to_map.get(class_idx, f"unknown_{class_idx}")
            
            # Добавление в историю для стабильности
            self._classification_history.append((map_id, confidence))
            if len(self._classification_history) > self._history_size:
                self._classification_history.pop(0)
            
            # Определение финального класса по большинству
            if len(self._classification_history) >= 3:
                map_counts = {}
                for mid, conf in self._classification_history:
                    map_counts[mid] = map_counts.get(mid, 0) + 1
                
                # Выбираем наиболее частый
                stable_map_id = max(map_counts.keys(), key=lambda k: map_counts[k])
                
                # Если есть явное большинство
                if map_counts[stable_map_id] >= len(self._classification_history) // 2 + 1:
                    map_id = stable_map_id
            
            # Обновление состояния
            old_map_id = self._current_map_id
            self._current_map_id = map_id
            self._current_confidence = confidence
            self._last_classification_time = current_time
            
            # Обновление метрик
            inference_time = (time.time() - start_time) * 1000
            self._update_metrics(inference_time)
            
            if old_map_id != map_id:
                self.metrics["map_changes"] += 1
                self.logger.info(f"Смена локации: {old_map_id} -> {map_id} (conf={confidence:.2f})")
            
            # Загрузка конфигурации карты если сменилась
            if old_map_id != map_id:
                self._load_map_config(map_id)
            
            return map_id
            
        except Exception as e:
            self.logger.error(f"Ошибка классификации: {e}", exc_info=True)
            return None
    
    def _prepare_input(self, frame: np.ndarray) -> np.ndarray:
        """Подготовка входного тензора"""
        try:
            import cv2
        except ImportError:
            cv2 = None
        
        if cv2:
            # Изменение размера
            resized = cv2.resize(frame, self.input_size)
            
            # BGR -> RGB
            rgb = cv2.cvtColor(resized, cv2.COLOR_BGR2RGB)
            
            # Нормализация
            normalized = rgb.astype(np.float32) / 255.0
            
            # Транспонирование HWC -> CHW
            transposed = np.transpose(normalized, (2, 0, 1))
            
            # Добавление батч-измерения
            batched = transposed[np.newaxis, ...].astype(np.float32)
        else:
            from PIL import Image
            img = Image.fromarray(frame)
            img = img.resize(self.input_size)
            arr = np.array(img, dtype=np.float32) / 255.0
            if len(arr.shape) == 3:
                arr = np.transpose(arr, (2, 0, 1))
            batched = arr[np.newaxis, ...]
        
        return batched
    
    def _process_output(self, outputs: list) -> Tuple[int, float]:
        """Обработка выхода модели"""
        output = outputs[0][0]  # Убираем батч
        
        # Softmax для получения вероятностей
        exp_output = np.exp(output - np.max(output))
        probabilities = exp_output / np.sum(exp_output)
        
        # Получаем индекс класса и уверенность
        class_idx = int(np.argmax(probabilities))
        confidence = float(probabilities[class_idx])
        
        return class_idx, confidence
    
    def _update_metrics(self, inference_time_ms: float):
        """Обновление метрик"""
        self.metrics["classification_count"] += 1
        
        alpha = 0.1
        self.metrics["avg_inference_time_ms"] = (
            alpha * inference_time_ms +
            (1 - alpha) * self.metrics["avg_inference_time_ms"]
        )
    
    def _load_map_config(self, map_id: str):
        """Загрузка конфигурации карты"""
        config_file = self.maps_config_dir / f"map_{map_id}.cfg"
        
        if config_file.exists():
            self.logger.info(f"Конфигурация карты загружена: {config_file}")
            # Здесь можно добавить логику применения конфигурации
        else:
            self.logger.warning(f"Конфигурация карты не найдена: {config_file}")
    
    def get_current_map(self) -> str:
        """Получение текущего ID карты"""
        return self._current_map_id
    
    def get_current_confidence(self) -> float:
        """Получение уверенности классификации"""
        return self._current_confidence
    
    def reset_history(self):
        """Сброс истории классификаций"""
        self._classification_history.clear()
        self.logger.debug("История классификаций сброшена")
    
    def is_loaded(self) -> bool:
        """Проверка загружена ли модель"""
        return self._session is not None
    
    def get_metrics(self) -> Dict[str, Any]:
        """Получение метрик"""
        return self.metrics.copy()
    
    def unload(self):
        """Выгрузка модели"""
        self._session = None
        self._input_name = None
        self._output_names = None
        self.logger.info("Classifier модель выгружена")
