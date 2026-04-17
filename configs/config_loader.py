"""
Загрузчик конфигурации
"""

import yaml
from pathlib import Path
from typing import Any, Dict


class ConfigLoader:
    """Класс для загрузки и управления конфигурацией"""
    
    _config: Dict[str, Any] = {}
    _config_path: str = ""
    
    @classmethod
    def load(cls, config_path: str = "configs/config.yaml") -> Dict[str, Any]:
        """
        Загрузка конфигурации из YAML файла
        
        Args:
            config_path: Путь к файлу конфигурации
            
        Returns:
            Словарь с конфигурацией
        """
        if cls._config and cls._config_path == config_path:
            return cls._config
        
        path = Path(config_path)
        if not path.exists():
            raise FileNotFoundError(f"Конфигурационный файл не найден: {config_path}")
        
        with open(path, 'r', encoding='utf-8') as f:
            cls._config = yaml.safe_load(f)
            cls._config_path = config_path
        
        return cls._config
    
    @classmethod
    def get(cls, *keys, default=None) -> Any:
        """
        Получение значения по ключам
        
        Args:
            *keys: Последовательность ключей для доступа к вложенным значениям
            default: Значение по умолчанию если ключ не найден
            
        Returns:
            Значение конфигурации или default
        """
        if not cls._config:
            cls.load()
        
        value = cls._config
        for key in keys:
            if isinstance(value, dict) and key in value:
                value = value[key]
            else:
                return default
        return value
    
    @classmethod
    def save(cls, config_path: str = None):
        """
        Сохранение текущей конфигурации в файл
        
        Args:
            config_path: Путь к файлу (если не указан, используется текущий)
        """
        if not config_path:
            config_path = cls._config_path
        
        if not config_path:
            raise ValueError("Путь к файлу конфигурации не указан")
        
        path = Path(config_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(path, 'w', encoding='utf-8') as f:
            yaml.dump(cls._config, f, allow_unicode=True, default_flow_style=False)
    
    @classmethod
    def update(cls, **kwargs):
        """
        Обновление конфигурации новыми значениями
        
        Args:
            **kwargs: Параметры для обновления
        """
        if not cls._config:
            cls.load()
        
        cls._config.update(kwargs)
    
    @classmethod
    def reset(cls):
        """Сброс загруженной конфигурации"""
        cls._config = {}
        cls._config_path = ""
