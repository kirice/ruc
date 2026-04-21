"""
Trainer - Инструмент для сбора пар «скрин→клик» и обучения модели
"""

import logging
import time
import json
from pathlib import Path
from typing import Optional, List, Dict, Any, Tuple
from datetime import datetime
import threading

try:
    import numpy as np
except ImportError:
    np = None


class DataPair:
    """Пара данных: скриншот + координата клика"""
    
    def __init__(self, frame_descriptor: str, x: float, y: float, 
                 confidence: float = 1.0, metadata: dict = None):
        self.frame_descriptor = frame_descriptor  # Хэш или путь к изображению
        self.x = x  # Нормализованная координата (-1..1)
        self.y = y
        self.confidence = confidence
        self.metadata = metadata or {}
        self.timestamp = time.time()
    
    def to_dict(self) -> dict:
        return {
            "frame_descriptor": self.frame_descriptor,
            "x": self.x,
            "y": self.y,
            "confidence": self.confidence,
            "metadata": self.metadata,
            "timestamp": self.timestamp
        }
    
    @classmethod
    def from_dict(cls, data: dict):
        return cls(
            frame_descriptor=data["frame_descriptor"],
            x=data["x"],
            y=data["y"],
            confidence=data.get("confidence", 1.0),
            metadata=data.get("metadata", {}),
            timestamp=data.get("timestamp", time.time())
        )


class Trainer:
    """
    Система сбора данных и обучения модели
    
    Режимы:
    - recording: Запись пар скриншот-клик
    - training: Обучение модели на собранных данных
    - validation: Валидация модели
    """
    
    def __init__(self, config: dict = None):
        self.config = config or {}
        self.logger = logging.getLogger("trainer")
        
        # Настройки
        trainer_config = self.config.get("trainer", {})
        self.datasets_dir = Path(trainer_config.get(
            "datasets_dir", "data/datasets"
        ))
        self.models_dir = Path(trainer_config.get(
            "models_dir", "models"
        ))
        
        # Состояние
        self._recording = False
        self._current_map_id: str = ""
        self._pending_frame: Optional[np.ndarray] = None
        self._collected_pairs: List[DataPair] = []
        
        # Callbacks
        self.on_pair_collected: Optional[callable] = None
        
        self.logger.info("Trainer инициализирован")
    
    def start_recording(self, map_id: str):
        """Начать запись пар для указанной карты"""
        self._recording = True
        self._current_map_id = map_id
        self._pending_frame = None
        self._collected_pairs = []
        
        # Создание директории для датасета
        dataset_path = self.datasets_dir / map_id / "pairs"
        dataset_path.mkdir(parents=True, exist_ok=True)
        
        self.logger.info(f"Запись начата для карты: {map_id}")
    
    def stop_recording(self) -> int:
        """Остановить запись и сохранить данные"""
        self._recording = False
        
        count = len(self._collected_pairs)
        if count > 0:
            self._save_pairs()
        
        self.logger.info(f"Запись остановлена. Собрано пар: {count}")
        self._current_map_id = ""
        return count
    
    def set_pending_frame(self, frame: np.ndarray):
        """Установить текущий кадр для записи"""
        if self._recording:
            self._pending_frame = frame.copy()
    
    def record_click(self, x: float, y: float, confidence: float = 1.0,
                     metadata: dict = None):
        """
        Записать пару: текущий кадр + координаты клика
        
        Args:
            x, y: Нормализованные координаты клика (-1..1)
            confidence: Уверенность в разметке
            metadata: Дополнительные метаданные
        """
        if not self._recording:
            self.logger.warning("Запись не активна")
            return False
        
        if self._pending_frame is None:
            self.logger.warning("Нет кадра для записи")
            return False
        
        try:
            # Сохранение кадра
            frame_path = self._save_frame(self._pending_frame)
            
            # Создание пары
            pair = DataPair(
                frame_descriptor=str(frame_path.relative_to(self.datasets_dir)),
                x=x,
                y=y,
                confidence=confidence,
                metadata=metadata or {"map_id": self._current_map_id}
            )
            
            self._collected_pairs.append(pair)
            
            # Callback
            if self.on_pair_collected:
                self.on_pair_collected(pair)
            
            self.logger.debug(f"Пара записана: ({x:.3f}, {y:.3f})")
            
            # Очистка pending кадра
            self._pending_frame = None
            
            return True
            
        except Exception as e:
            self.logger.error(f"Ошибка записи пары: {e}", exc_info=True)
            return False
    
    def _save_frame(self, frame: np.ndarray) -> Path:
        """Сохранение кадра в датасет"""
        try:
            import cv2
        except ImportError:
            cv2 = None
        
        dataset_path = self.datasets_dir / self._current_map_id / "pairs"
        dataset_path.mkdir(parents=True, exist_ok=True)
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        filename = f"frame_{timestamp}.png"
        filepath = dataset_path / filename
        
        if cv2 is not None:
            cv2.imwrite(str(filepath), frame)
        else:
            from PIL import Image
            img = Image.fromarray(frame)
            img.save(filepath)
        
        return filepath
    
    def _save_pairs(self):
        """Сохранение собранных пар в JSON"""
        if not self._collected_pairs:
            return
        
        dataset_path = self.datasets_dir / self._current_map_id
        pairs_file = dataset_path / "pairs.json"
        
        # Загрузка существующих пар если есть
        existing_pairs = []
        if pairs_file.exists():
            try:
                with open(pairs_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    existing_pairs = [DataPair.from_dict(d) for d in data]
            except Exception as e:
                self.logger.warning(f"Не удалось загрузить существующие пары: {e}")
        
        # Объединение
        all_pairs = existing_pairs + self._collected_pairs
        
        # Сохранение
        with open(pairs_file, 'w', encoding='utf-8') as f:
            json.dump([p.to_dict() for p in all_pairs], f, indent=2, ensure_ascii=False)
        
        self.logger.info(f"Пары сохранены: {pairs_file} (всего: {len(all_pairs)})")
    
    def get_dataset_stats(self, map_id: str) -> Dict[str, Any]:
        """Получение статистики датасета"""
        dataset_path = self.datasets_dir / map_id
        
        stats = {
            "map_id": map_id,
            "pairs_count": 0,
            "frames_count": 0,
            "avg_confidence": 0.0
        }
        
        pairs_file = dataset_path / "pairs.json"
        if pairs_file.exists():
            try:
                with open(pairs_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    stats["pairs_count"] = len(data)
                    
                    if data:
                        confidences = [d.get("confidence", 1.0) for d in data]
                        stats["avg_confidence"] = sum(confidences) / len(confidences)
            except Exception as e:
                self.logger.error(f"Ошибка чтения статистики: {e}")
        
        # Подсчёт кадров
        frames_dir = dataset_path / "pairs"
        if frames_dir.exists():
            stats["frames_count"] = len(list(frames_dir.glob("*.png")))
        
        return stats
    
    def load_dataset(self, map_id: str) -> List[DataPair]:
        """Загрузка датасета для карты"""
        pairs_file = self.datasets_dir / map_id / "pairs.json"
        
        if not pairs_file.exists():
            self.logger.warning(f"Датасет не найден: {pairs_file}")
            return []
        
        try:
            with open(pairs_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                pairs = [DataPair.from_dict(d) for d in data]
            
            self.logger.info(f"Датасет загружен: {len(pairs)} пар")
            return pairs
            
        except Exception as e:
            self.logger.error(f"Ошибка загрузки датасета: {e}")
            return []
    
    def export_for_training(self, map_id: str, output_dir: str) -> bool:
        """
        Экспорт датасета в формат для обучения
        
        Args:
            map_id: ID карты
            output_dir: Директория для экспорта
            
        Returns:
            True если успешно
        """
        try:
            pairs = self.load_dataset(map_id)
            
            if not pairs:
                self.logger.warning("Нет данных для экспорта")
                return False
            
            output_path = Path(output_dir)
            output_path.mkdir(parents=True, exist_ok=True)
            
            # Разделение на train/val
            split_idx = int(len(pairs) * 0.8)
            train_pairs = pairs[:split_idx]
            val_pairs = pairs[split_idx:]
            
            # Сохранение
            with open(output_path / "train.json", 'w', encoding='utf-8') as f:
                json.dump([p.to_dict() for p in train_pairs], f, indent=2)
            
            with open(output_path / "val.json", 'w', encoding='utf-8') as f:
                json.dump([p.to_dict() for p in val_pairs], f, indent=2)
            
            # Копирование изображений
            self._copy_images_for_export(map_id, output_path, train_pairs, val_pairs)
            
            self.logger.info(f"Датасет экспортирован: {output_path}")
            return True
            
        except Exception as e:
            self.logger.error(f"Ошибка экспорта: {e}", exc_info=True)
            return False
    
    def _copy_images_for_export(self, map_id: str, output_path: Path,
                                 train_pairs: list, val_pairs: list):
        """Копирование изображений для экспорта"""
        import shutil
        
        src_base = self.datasets_dir / map_id / "pairs"
        
        # Создаём директории
        (output_path / "images" / "train").mkdir(parents=True, exist_ok=True)
        (output_path / "images" / "val").mkdir(parents=True, exist_ok=True)
        
        for pair_set, subset in [(train_pairs, "train"), (val_pairs, "val")]:
            for pair in pair_set:
                src_file = self.datasets_dir / pair.frame_descriptor
                if src_file.exists():
                    dst_file = output_path / "images" / subset / src_file.name
                    shutil.copy2(src_file, dst_file)
    
    def is_recording(self) -> bool:
        """Проверка активности записи"""
        return self._recording
    
    def get_current_map(self) -> str:
        """Получение текущего ID карты"""
        return self._current_map_id
    
    def get_pending_frame(self) -> Optional[np.ndarray]:
        """Получение текущего pending кадра"""
        return self._pending_frame
    
    def clear_pending_frame(self):
        """Очистка pending кадра"""
        self._pending_frame = None
