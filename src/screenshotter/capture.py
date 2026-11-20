"""
Скриншотер - автоматические скриншоты из BlueStacks с сортировкой
"""

import logging
import time
import shutil
from pathlib import Path
from datetime import datetime
from typing import Optional
import threading


class Screenshotter:
    """Автоматический скриншотер с сортировкой"""
    
    def __init__(self, config: dict, bluestacks_manager):
        self.config = config
        self.bluestacks = bluestacks_manager
        self.logger = logging.getLogger("screenshotter")
        
        # Настройки из конфига
        ss_config = config.get("screenshotter", {})
        self.interval = ss_config.get("interval", 2.0)
        self.raw_folder = Path(ss_config.get("raw_folder", "data/raw"))
        self.labeled_folder = Path(ss_config.get("labeled_folder", "data/labeled"))
        self.rejected_folder = Path(ss_config.get("rejected_folder", "data/rejected"))
        
        # Создание папок
        self.raw_folder.mkdir(parents=True, exist_ok=True)
        self.labeled_folder.mkdir(parents=True, exist_ok=True)
        self.rejected_folder.mkdir(parents=True, exist_ok=True)
        
        # Состояние
        self._capturing = False
        self._thread = None
    
    def start_capture(self):
        """Запуск автоматического создания скриншотов"""
        if self._capturing:
            return
        
        self._capturing = True
        self.logger.info(f"Запуск скриншотера (интервал: {self.interval}с)")
        
        self._thread = threading.Thread(target=self._capture_loop, daemon=True)
        self._thread.start()
    
    def stop_capture(self):
        """Остановка создания скриншотов"""
        self._capturing = False
        if self._thread:
            self._thread.join(timeout=5)
        self.logger.info("Скриншотер остановлен")
    
    def _capture_loop(self):
        """Цикл автоматического создания скриншотов"""
        while self._capturing:
            try:
                self.capture_screenshot()
                time.sleep(self.interval)
            except Exception as e:
                self.logger.error(f"Ошибка в цикле скриншотов: {e}")
                time.sleep(1)
    
    def capture_screenshot(self, auto_sort: bool = True) -> Optional[Path]:
        """
        Создание скриншота
        
        Args:
            auto_sort: Автоматически сортировать скриншот
            
        Returns:
            Путь к сохраненному файлу или None
        """
        try:
            # Получение скриншота от BlueStacks
            screenshot_data = self.bluestacks.take_screenshot()
            
            if screenshot_data is None:
                self.logger.warning("Не удалось получить скриншот")
                return None
            
            # Генерация имени файла
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
            filename = f"screenshot_{timestamp}.png"
            filepath = self.raw_folder / filename
            
            # Сохранение
            with open(filepath, 'wb') as f:
                f.write(screenshot_data)
            
            self.logger.debug(f"Скриншот сохранен: {filepath}")
            
            # Автоматическая сортировка
            if auto_sort:
                self._auto_sort(filepath)
            
            return filepath
            
        except Exception as e:
            self.logger.error(f"Ошибка создания скриншота: {e}", exc_info=True)
            return None
    
    def _auto_sort(self, filepath: Path):
        """
        Автоматическая сортировка скриншота
        
        Args:
            filepath: Путь к файлу скриншота
        """
        try:
            import cv2
            import numpy as np
            
            # Загрузка изображения
            img = cv2.imread(str(filepath))
            
            if img is None:
                self.move_to_rejected(filepath, reason="Не удалось прочитать")
                return
            
            # Проверка на "черный экран"
            if self._is_black_screen(img):
                self.move_to_rejected(filepath, reason="Черный экран")
                return
            
            # Проверка на меню/инвентарь (можно добавить детекцию)
            if self._is_ui_screen(img):
                self.move_to_rejected(filepath, reason="UI экран")
                return
            
            # Оставляем в raw для последующей разметки
            self.logger.debug(f"Скриншот прошел проверку: {filepath}")
            
        except Exception as e:
            self.logger.error(f"Ошибка сортировки: {e}")
    
    def _is_black_screen(self, img: np.ndarray, threshold: int = 10) -> bool:
        """
        Проверка на черный экран
        
        Args:
            img: Изображение
            threshold: Порог яркости
            
        Returns:
            True если экран черный
        """
        mean_brightness = img.mean()
        return mean_brightness < threshold
    
    def _is_ui_screen(self, img: np.ndarray) -> bool:
        """
        Проверка на наличие UI элементов (меню, инвентарь)
        
        Здесь можно реализовать детекцию UI через:
        - Анализ гистограммы
        - Детекцию прямых линий
        - ML модель
        
        Args:
            img: Изображение
            
        Returns:
            True если это UI экран
        """
        # Заглушка - можно расширить
        return False
    
    def move_to_labeled(self, filepath: Path):
        """Перемещение в папку размеченных"""
        dest = self.labeled_folder / filepath.name
        shutil.move(str(filepath), str(dest))
        self.logger.info(f"Перемещено в labeled: {dest}")
    
    def move_to_rejected(self, filepath: Path, reason: str = ""):
        """Перемещение в брак"""
        dest = self.rejected_folder / filepath.name
        shutil.move(str(filepath), str(dest))
        self.logger.info(f"Перемещено в rejected ({reason}): {dest}")
    
    def get_statistics(self) -> dict:
        """Получение статистики по папкам"""
        return {
            "raw": len(list(self.raw_folder.glob("*.png"))),
            "labeled": len(list(self.labeled_folder.glob("*.png"))),
            "rejected": len(list(self.rejected_folder.glob("*.png"))),
        }


class ImageSorterGUI:
    """Простой интерфейс для ручной сортировки изображений"""
    
    def __init__(self, screenshotter: Screenshotter):
        self.screenshotter = screenshotter
        self.logger = logging.getLogger("image_sorter_gui")
        self.current_image = None
        self.current_path = None
    
    def show_next_image(self):
        """Показать следующее изображение для сортировки"""
        # Получаем первый файл из raw
        raw_files = list(self.screenshotter.raw_folder.glob("*.png"))
        
        if not raw_files:
            self.logger.info("Нет изображений для сортировки")
            return None
        
        self.current_path = raw_files[0]
        
        try:
            import cv2
            self.current_image = cv2.imread(str(self.current_path))
            return self.current_image
        except Exception as e:
            self.logger.error(f"Ошибка загрузки: {e}")
            return None
    
    def sort_current(self, category: str):
        """
        Сортировка текущего изображения
        
        Args:
            category: "labeled" или "rejected"
        """
        if self.current_path is None:
            return
        
        if category == "labeled":
            self.screenshotter.move_to_labeled(self.current_path)
        elif category == "rejected":
            self.screenshotter.move_to_rejected(self.current_path)
        
        self.current_image = None
        self.current_path = None
