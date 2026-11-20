"""
Модуль обучения нейросети - тренировка модели для обнаружения мобов
"""

import logging
from pathlib import Path
from typing import Optional, Dict, Any
import yaml


class ModelTrainer:
    """Тренеровщик нейросети для обнаружения мобов"""
    
    def __init__(self, config: dict):
        self.config = config
        self.logger = logging.getLogger("model_trainer")
        
        # Настройки из конфига
        train_config = config.get("training", {})
        self.image_size = train_config.get("image_size", 640)
        self.epochs = train_config.get("epochs", 100)
        self.batch_size = train_config.get("batch_size", 16)
        self.val_split = train_config.get("val_split", 0.2)
        self.device = train_config.get("device", "cuda")
    
    def prepare_dataset(self, data_dir: str = "data/labeled") -> bool:
        """
        Подготовка датасета для обучения
        
        Args:
            data_dir: Папка с размеченными данными
            
        Returns:
            True если подготовка успешна
        """
        self.logger.info(f"Подготовка датасета из {data_dir}")
        
        data_path = Path(data_dir)
        if not data_path.exists():
            self.logger.error(f"Папка данных не найдена: {data_path}")
            return False
        
        # Проверка структуры YOLO
        required_files = ["data.yaml", "images", "labels"]
        for item in required_files:
            if not (data_path / item).exists():
                self.logger.warning(f"Отсутствует: {item}")
        
        # Создание конфигурационного файла для YOLO
        self._create_yolo_config(data_path)
        
        self.logger.info("Датасет подготовлен")
        return True
    
    def _create_yolo_config(self, data_path: Path):
        """Создание YAML конфигурации для YOLO"""
        config = {
            "path": str(data_path.absolute()),
            "train": "images/train",
            "val": "images/val",
            "nc": 1,  # Количество классов (мобы)
            "names": ["mob"]  # Названия классов
        }
        
        config_file = data_path / "data.yaml"
        with open(config_file, 'w', encoding='utf-8') as f:
            yaml.dump(config, f, allow_unicode=True)
        
        self.logger.info(f"Конфигурация YOLO создана: {config_file}")
    
    def train(self, model_type: str = "yolov8n", 
              output_path: str = "models/model.onnx") -> bool:
        """
        Запуск процесса обучения
        
        Args:
            model_type: Тип модели (yolov8n, yolov8s, etc.)
            output_path: Путь для сохранения обученной модели
            
        Returns:
            True если обучение успешно
        """
        self.logger.info(f"Запуск обучения модели: {model_type}")
        
        try:
            from ultralytics import YOLO
            
            # Загрузка предобученной модели
            model = YOLO(f"{model_type}.pt")
            
            # Обучение
            results = model.train(
                data="data/labeled/data.yaml",
                epochs=self.epochs,
                imgsz=self.image_size,
                batch=self.batch_size,
                device=self.device,
                verbose=True
            )
            
            # Сохранение в ONNX
            self._export_to_onnx(model, output_path)
            
            self.logger.info("Обучение завершено")
            return True
            
        except ImportError:
            self.logger.error("Установите ultralytics: pip install ultralytics")
            return False
        except Exception as e:
            self.logger.error(f"Ошибка обучения: {e}", exc_info=True)
            return False
    
    def _export_to_onnx(self, model, output_path: str):
        """Экспорт модели в ONNX формат"""
        try:
            Path(output_path).parent.mkdir(parents=True, exist_ok=True)
            
            model.export(format="onnx", save_path=output_path)
            
            self.logger.info(f"Модель экспортирована в ONNX: {output_path}")
            
        except Exception as e:
            self.logger.error(f"Ошибка экспорта в ONNX: {e}")
    
    def validate(self, model_path: str, test_data: str) -> Dict[str, Any]:
        """
        Валидация модели на тестовых данных
        
        Args:
            model_path: Путь к модели
            test_data: Папка с тестовыми данными
            
        Returns:
            Статистика качества модели
        """
        self.logger.info(f"Валидация модели: {model_path}")
        
        try:
            from ultralytics import YOLO
            
            model = YOLO(model_path)
            
            # Запуск валидации
            metrics = model.val(data=test_data)
            
            stats = {
                "mAP50": metrics.box.map50,
                "mAP50-95": metrics.box.map,
                "precision": metrics.box.mp,
                "recall": metrics.box.mr,
            }
            
            self.logger.info(f"Результаты валидации: {stats}")
            return stats
            
        except Exception as e:
            self.logger.error(f"Ошибка валидации: {e}")
            return {}
    
    def run_training_pipeline(self, data_dir: str = "data/labeled",
                              output_path: str = "models/model.onnx") -> bool:
        """
        Полный пайплайн обучения
        
        Args:
            data_dir: Папка с данными
            output_path: Путь для сохранения модели
            
        Returns:
            True если всё успешно
        """
        self.logger.info("Запуск полного пайплайна обучения")
        
        # 1. Подготовка данных
        if not self.prepare_dataset(data_dir):
            return False
        
        # 2. Обучение
        if not self.train(output_path=output_path):
            return False
        
        # 3. Валидация (опционально)
        # stats = self.validate(output_path, data_dir)
        
        return True


def main():
    """CLI для запуска обучения"""
    import argparse
    
    parser = argparse.ArgumentParser(description="Обучение модели для бота")
    parser.add_argument("--data", type=str, default="data/labeled",
                       help="Папка с размеченными данными")
    parser.add_argument("--output", type=str, default="models/model.onnx",
                       help="Путь для сохранения модели")
    parser.add_argument("--epochs", type=int, default=100,
                       help="Количество эпох")
    parser.add_argument("--model", type=str, default="yolov8n",
                       help="Тип модели")
    
    args = parser.parse_args()
    
    # Загрузка конфига
    from configs.config_loader import ConfigLoader
    config = ConfigLoader.load()
    
    # Обновление настроек
    if args.epochs:
        config["training"]["epochs"] = args.epochs
    
    trainer = ModelTrainer(config)
    success = trainer.run_training_pipeline(args.data, args.output)
    
    if success:
        print("✅ Обучение завершено успешно!")
    else:
        print("❌ Ошибка обучения")


if __name__ == "__main__":
    main()
