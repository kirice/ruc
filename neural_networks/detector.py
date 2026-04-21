"""
Detector (NN-1) - Детекция объектов. Анализирует кадр, выделяет игровые сущности 
(мобы, препятствия, порталы). Выдаёт координаты, классы объектов и степень уверенности.
"""

import logging
from pathlib import Path
from typing import List, Dict, Any, Optional
import numpy as np

try:
    import onnxruntime as ort
except ImportError:
    ort = None


class Detector:
    """
    Модель детекции объектов для ситуативных реакций
    
    Вход: Кадр изображения
    Выход: Список обнаруженных объектов с координатами, классами и уверенностью
    """
    
    def __init__(self, config: dict = None):
        self.config = config or {}
        self.logger = logging.getLogger("detector")
        
        # Настройки
        model_config = self.config.get("detector", {})
        self.input_size = tuple(model_config.get("input_size", (640, 640)))
        self.confidence_threshold = model_config.get("confidence_threshold", 0.5)
        self.iou_threshold = model_config.get("iou_threshold", 0.45)
        self.default_model_path = model_config.get("default_model_path", "models/nn_det_default.onnx")
        
        # Классы объектов
        self.class_names = model_config.get("class_names", ["mob", "obstacle", "portal", "item"])
        
        # Состояние
        self._session: Optional[ort.InferenceSession] = None
        self._input_name: Optional[str] = None
        self._output_names: Optional[list] = None
        self._loaded_model_path: str = ""
        
        # Метрики
        self.metrics = {
            "detection_count": 0,
            "objects_detected": 0,
            "avg_inference_time_ms": 0.0
        }
        
        self.logger.info("Detector инициализирован")
    
    def load_model(self, model_path: str) -> bool:
        """
        Загрузка модели детектора
        
        Args:
            model_path: Путь к ONNX модели
            
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
            
            self.logger.info(f"Detector модель загружена: {model_path}")
            return True
            
        except Exception as e:
            self.logger.error(f"Ошибка загрузки модели детектора: {e}", exc_info=True)
            return False
    
    def detect(self, frame: np.ndarray) -> List[Dict[str, Any]]:
        """
        Детекция объектов на кадре
        
        Args:
            frame: Кадр изображения (BGR или RGB)
            
        Returns:
            Список обнаруженных объектов
        """
        if self._session is None:
            return []
        
        if frame is None:
            return []
        
        try:
            import time
            start_time = time.time()
            
            # Предобработка
            input_tensor = self._prepare_input(frame)
            
            # Инференс
            outputs = self._session.run(self._output_names, {self._input_name: input_tensor})
            
            # Постобработка
            objects = self._postprocess(outputs, frame.shape)
            
            # Обновление метрик
            inference_time = (time.time() - start_time) * 1000
            self._update_metrics(inference_time, len(objects))
            
            return objects
            
        except Exception as e:
            self.logger.error(f"Ошибка детекции: {e}", exc_info=True)
            return []
    
    def _prepare_input(self, frame: np.ndarray) -> np.ndarray:
        """Подготовка входного тензора"""
        try:
            import cv2
        except ImportError:
            cv2 = None
        
        if cv2:
            # Изменение размера
            resized = cv2.resize(frame, self.input_size)
            
            # BGR -> RGB если нужно
            if len(resized.shape) == 3 and resized.shape[2] == 3:
                rgb = cv2.cvtColor(resized, cv2.COLOR_BGR2RGB)
            else:
                rgb = resized
            
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
    
    def _postprocess(self, outputs: list, original_shape: tuple) -> List[Dict[str, Any]]:
        """Постобработка результатов детекции"""
        objects = []
        
        try:
            # Обработка в зависимости от формата выхода модели
            # Предполагаем YOLO-like формат: [batch, num_detections, 6] где 6 = (x1, y1, x2, y2, conf, class)
            
            output = outputs[0][0]  # Убираем батч
            
            for detection in output:
                if len(detection) < 6:
                    continue
                
                x1, y1, x2, y2, confidence, class_id = detection[:6]
                
                # Фильтрация по уверенности
                if confidence < self.confidence_threshold:
                    continue
                
                # Конвертация координат в оригинальное разрешение
                scale_x = original_shape[1] / self.input_size[0]
                scale_y = original_shape[0] / self.input_size[1]
                
                x1_orig = int(x1 * scale_x)
                y1_orig = int(y1 * scale_y)
                x2_orig = int(x2 * scale_x)
                y2_orig = int(y2 * scale_y)
                
                # Получение имени класса
                class_idx = int(class_id) % len(self.class_names)
                class_name = self.class_names[class_idx]
                
                objects.append({
                    "class": class_name,
                    "class_id": class_idx,
                    "confidence": float(confidence),
                    "bbox": (x1_orig, y1_orig, x2_orig, y2_orig),
                    "center": ((x1_orig + x2_orig) // 2, (y1_orig + y2_orig) // 2)
                })
            
            # NMS (Non-Maximum Suppression) если нужно
            if len(objects) > 1:
                objects = self._apply_nms(objects)
            
        except Exception as e:
            self.logger.error(f"Ошибка постобработки: {e}")
        
        return objects
    
    def _apply_nms(self, objects: List[Dict]) -> List[Dict]:
        """Применение Non-Maximum Suppression"""
        if not objects:
            return []
        
        try:
            # Сортировка по уверенности
            objects.sort(key=lambda x: x["confidence"], reverse=True)
            
            selected = []
            
            while objects:
                best = objects.pop(0)
                selected.append(best)
                
                # Удаление перекрытий
                objects = [
                    obj for obj in objects
                    if self._iou(best["bbox"], obj["bbox"]) < self.iou_threshold
                ]
            
            return selected
            
        except Exception as e:
            self.logger.error(f"Ошибка NMS: {e}")
            return objects[:1]  # Возвращаем хотя бы первый объект
    
    def _iou(self, box1: tuple, box2: tuple) -> float:
        """Вычисление IoU (Intersection over Union)"""
        x1_min, y1_min, x1_max, y1_max = box1
        x2_min, y2_min, x2_max, y2_max = box2
        
        # Пересечение
        inter_x_min = max(x1_min, x2_min)
        inter_y_min = max(y1_min, y2_min)
        inter_x_max = min(x1_max, x2_max)
        inter_y_max = min(y1_max, y2_max)
        
        if inter_x_max <= inter_x_min or inter_y_max <= inter_y_min:
            return 0.0
        
        inter_area = (inter_x_max - inter_x_min) * (inter_y_max - inter_y_min)
        
        # Площади
        area1 = (x1_max - x1_min) * (y1_max - y1_min)
        area2 = (x2_max - x2_min) * (y2_max - y2_min)
        
        union_area = area1 + area2 - inter_area
        
        return inter_area / union_area if union_area > 0 else 0.0
    
    def _update_metrics(self, inference_time_ms: float, objects_count: int):
        """Обновление метрик"""
        self.metrics["detection_count"] += 1
        self.metrics["objects_detected"] += objects_count
        
        alpha = 0.1
        self.metrics["avg_inference_time_ms"] = (
            alpha * inference_time_ms +
            (1 - alpha) * self.metrics["avg_inference_time_ms"]
        )
    
    def get_objects_by_class(self, objects: List[Dict], class_name: str) -> List[Dict]:
        """Фильтрация объектов по классу"""
        return [obj for obj in objects if obj["class"] == class_name]
    
    def get_nearest_object(self, objects: List[Dict], 
                           reference_point: tuple) -> Optional[Dict]:
        """Поиск ближайшего объекта к точке"""
        if not objects:
            return None
        
        ref_x, ref_y = reference_point
        min_distance = float('inf')
        nearest = None
        
        for obj in objects:
            center = obj["center"]
            distance = ((center[0] - ref_x) ** 2 + (center[1] - ref_y) ** 2) ** 0.5
            
            if distance < min_distance:
                min_distance = distance
                nearest = obj
        
        return nearest
    
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
        self.logger.info("Detector модель выгружена")
