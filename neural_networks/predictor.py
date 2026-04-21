"""
Predictor (NN-2) - Прямой предиктор действий. Stateless-модель регрессии.
Принцип работы: «увидел кадр → предсказал координату клика»
"""

import logging
from pathlib import Path
from typing import Optional, Tuple, Dict, Any
import numpy as np

try:
    import onnxruntime as ort
except ImportError:
    ort = None


class Predictor:
    """
    Регрессионная модель для предсказания координат клика
    
    Вход: Нормализованный скриншот текущего состояния экрана
    Выход: Вектор (X, Y) относительно центра окна + скаляр уверенности
    """
    
    def __init__(self, config: dict = None):
        self.config = config or {}
        self.logger = logging.getLogger("predictor")
        
        # Настройки
        model_config = self.config.get("model", {})
        self.input_size = tuple(model_config.get("input_size", (640, 640)))
        self.confidence_threshold = model_config.get("confidence_threshold", 0.7)
        self.default_model_path = model_config.get("default_model_path", "models/predictor_default.onnx")
        
        # Состояние
        self._session: Optional[ort.InferenceSession] = None
        self._input_name: Optional[str] = None
        self._output_names: Optional[list] = None
        self._current_map_id: str = ""
        self._loaded_model_path: str = ""
        
        # Метрики
        self.metrics = {
            "inference_count": 0,
            "avg_inference_time_ms": 0.0,
            "last_confidence": 0.0
        }
        
        self.logger.info("Predictor инициализирован")
    
    def load_model(self, model_path: str, map_id: str = "") -> bool:
        """
        Загрузка модели предиктора
        
        Args:
            model_path: Путь к ONNX модели
            map_id: ID карты (для контекста)
            
        Returns:
            True если загрузка успешна
        """
        try:
            if ort is None:
                self.logger.error("onnxruntime не установлен")
                return False
            
            path = Path(model_path)
            if not path.exists():
                self.logger.warning(f"Модель не найдена: {model_path}")
                # Попытка загрузить дефолтную
                default_path = Path(self.default_model_path)
                if default_path.exists():
                    model_path = str(default_path)
                else:
                    return False
            
            # Создание сессии
            providers = ['CUDAExecutionProvider', 'CPUExecutionProvider']
            self._session = ort.InferenceSession(model_path, providers=providers)
            
            self._input_name = self._session.get_inputs()[0].name
            self._output_names = [o.name for o in self._session.get_outputs()]
            
            self._loaded_model_path = model_path
            self._current_map_id = map_id
            
            self.logger.info(f"Модель загружена: {model_path} (карта: {map_id})")
            return True
            
        except Exception as e:
            self.logger.error(f"Ошибка загрузки модели: {e}", exc_info=True)
            return False
    
    def predict(self, frame: np.ndarray) -> Optional[Tuple[float, float, float]]:
        """
        Предсказание координаты клика
        
        Args:
            frame: Нормализованный кадр (HWC, RGB, 0-1)
            
        Returns:
            (x, y, confidence) или None при ошибке
            x, y - нормализованные координаты от -1 до 1 (центр = 0, 0)
        """
        if self._session is None:
            return None
        
        if frame is None:
            return None
        
        try:
            import time
            start_time = time.time()
            
            # Подготовка входа
            input_tensor = self._prepare_input(frame)
            
            # Инференс
            outputs = self._session.run(self._output_names, {self._input_name: input_tensor})
            
            # Обработка выхода
            prediction = self._process_output(outputs)
            
            # Обновление метрик
            inference_time = (time.time() - start_time) * 1000
            self._update_metrics(inference_time, prediction[2] if prediction else 0.0)
            
            # Логирование
            self._log_prediction(prediction)
            
            return prediction
            
        except Exception as e:
            self.logger.error(f"Ошибка инференса: {e}", exc_info=True)
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
            
            # Транспонирование HWC -> CHW
            if len(resized.shape) == 3:
                transposed = np.transpose(resized, (2, 0, 1))
            else:
                transposed = resized[np.newaxis, ...]
            
            # Добавление батч-измерения
            batched = transposed[np.newaxis, ...].astype(np.float32)
        else:
            # Fallback без OpenCV
            from PIL import Image
            img = Image.fromarray((frame * 255).astype(np.uint8))
            img = img.resize(self.input_size)
            arr = np.array(img, dtype=np.float32) / 255.0
            if len(arr.shape) == 3:
                arr = np.transpose(arr, (2, 0, 1))
            batched = arr[np.newaxis, ...]
        
        return batched
    
    def _process_output(self, outputs: list) -> Optional[Tuple[float, float, float]]:
        """Обработка выхода модели"""
        try:
            # Ожидаем выход [batch, 3] где 3 = (x, y, confidence)
            output = outputs[0][0]  # Убираем батч-измерение
            
            if len(output) >= 3:
                x = float(output[0])
                y = float(output[1])
                confidence = float(output[2]) if len(output) > 2 else 0.5
                
                # Clamp значений
                x = max(-1.0, min(1.0, x))
                y = max(-1.0, min(1.0, y))
                confidence = max(0.0, min(1.0, confidence))
                
                return (x, y, confidence)
            elif len(output) == 2:
                # Только координаты без уверенности
                x = float(output[0])
                y = float(output[1])
                return (max(-1.0, min(1.0, x)), max(-1.0, min(1.0, y)), 0.5)
            else:
                self.logger.warning(f"Неожиданный формат выхода: {len(output)}")
                return None
                
        except Exception as e:
            self.logger.error(f"Ошибка обработки выхода: {e}")
            return None
    
    def _update_metrics(self, inference_time_ms: float, confidence: float):
        """Обновление метрик"""
        self.metrics["inference_count"] += 1
        
        # Скользящее среднее времени инференса
        alpha = 0.1
        self.metrics["avg_inference_time_ms"] = (
            alpha * inference_time_ms + 
            (1 - alpha) * self.metrics["avg_inference_time_ms"]
        )
        
        self.metrics["last_confidence"] = confidence
    
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
            f.write(
                f"{timestamp} - NN2: x={x:.4f}, y={y:.4f}, conf={confidence:.4f}, "
                f"map={self._current_map_id}\n"
            )
    
    def get_current_model(self) -> str:
        """Получение пути к текущей модели"""
        return self._loaded_model_path
    
    def get_current_map(self) -> str:
        """Получение текущего ID карты"""
        return self._current_map_id
    
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
        self._loaded_model_path = ""
        self._current_map_id = ""
        self.logger.info("Модель выгружена")
