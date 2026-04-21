"""
Exporter - Создание EXE-версии приложения (Bot-EXE)
Упаковка ядра, моделей и конфигураций в самодостаточный пакет
"""

import logging
import subprocess
import shutil
import json
from pathlib import Path
from typing import List, Dict, Any, Optional
from datetime import datetime


class Exporter:
    """
    Экспортёр для создания автономной EXE-версии бота
    
    Функции:
    - Анализ зависимостей
    - Исключение отладочных модулей
    - Упаковка интерпретатора и моделей
    - Минимизация веса
    - Проверка целостности
    """
    
    def __init__(self, config: dict = None):
        self.config = config or {}
        self.logger = logging.getLogger("exporter")
        
        # Настройки
        export_config = self.config.get("exporter", {})
        self.output_dir = Path(export_config.get("output_dir", "dist"))
        self.build_dir = Path(export_config.get("build_dir", "build"))
        self.spec_file = export_config.get("spec_file", "bot.spec")
        
        # Пути проекта
        self.project_root = Path(export_config.get("project_root", "."))
        
        # Модули для исключения из сборки
        self.exclude_modules = [
            # Инструменты разработки
            "tools.trainer",
            "tools.training",
            # Отладочные GUI компоненты
            "gui.trainer_overlay",
            "gui.debug_panel",
            # Тесты
            "tests",
            "pytest",
        ]
        
        # Модули для включения (ядро)
        self.include_modules = [
            "core.action_loop",
            "core.scheduler",
            "core.state_machine",
            "emulator.bridge",
            "neural_networks.predictor",
            "neural_networks.detector",
            "neural_networks.context_classifier",
            "gui.dashboard",
            "gui.consoles",
        ]
        
        self.logger.info("Exporter инициализирован")
    
    def create_exe(self, profile: str = "default", 
                   output_name: str = "BotWorker") -> bool:
        """
        Создание EXE файла
        
        Args:
            profile: Профиль сборки (full, worker, exe)
            output_name: Имя выходного файла
            
        Returns:
            True если сборка успешна
        """
        self.logger.info(f"Начало сборки: {profile} -> {output_name}.exe")
        
        try:
            # 1. Подготовка директорий
            self._prepare_directories()
            
            # 2. Генерация spec файла
            spec_path = self._generate_spec(profile, output_name)
            
            # 3. Запуск PyInstaller
            success = self._run_pyinstaller(spec_path)
            
            if not success:
                return False
            
            # 4. Копирование ресурсов
            self._copy_resources(profile)
            
            # 5. Проверка целостности
            integrity_ok = self._verify_integrity(output_name)
            
            if not integrity_ok:
                self.logger.error("Проверка целостности не пройдена")
                return False
            
            # 6. Создание манифеста
            self._create_manifest(profile, output_name)
            
            self.logger.info(f"Сборка завершена: {self.output_dir / output_name}")
            return True
            
        except Exception as e:
            self.logger.error(f"Ошибка сборки: {e}", exc_info=True)
            return False
    
    def _prepare_directories(self):
        """Подготовка рабочих директорий"""
        # Очистка старых сборок
        if self.build_dir.exists():
            shutil.rmtree(self.build_dir)
        
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.build_dir.mkdir(parents=True, exist_ok=True)
        
        self.logger.debug("Директории подготовлены")
    
    def _generate_spec(self, profile: str, output_name: str) -> Path:
        """Генерация spec файла для PyInstaller"""
        
        # Определение включаемых модулей в зависимости от профиля
        if profile == "exe":
            # Минимальная версия - только ядро
            hidden_imports = [
                "core.action_loop",
                "core.scheduler",
                "emulator.bridge",
                "neural_networks.predictor",
            ]
            exclude_patterns = ["trainer", "debug", "test"]
        elif profile == "worker":
            # Рабочая версия
            hidden_imports = self.include_modules.copy()
            exclude_patterns = ["trainer", "test"]
        else:  # full
            # Полная версия
            hidden_imports = self.include_modules + ["tools.trainer"]
            exclude_patterns = ["test"]
        
        spec_content = f'''
# -*- mode: python ; coding: utf-8 -*-

block_cipher = None

a = Analysis(
    ['src/main.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('config', 'config'),
        ('models', 'models'),
    ],
    hiddenimports={hidden_imports},
    hookspath=[],
    hooksconfig={{}},
    runtime_hooks=[],
    excludes={self.exclude_modules},
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='{output_name}',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='icon.ico' if Path('icon.ico').exists() else None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='{output_name}',
)
'''
        
        spec_path = self.project_root / f"{output_name}.spec"
        with open(spec_path, 'w', encoding='utf-8') as f:
            f.write(spec_content)
        
        self.logger.info(f"Spec файл создан: {spec_path}")
        return spec_path
    
    def _run_pyinstaller(self, spec_path: Path) -> bool:
        """Запуск PyInstaller"""
        try:
            cmd = [
                "pyinstaller",
                "--clean",
                "--noconfirm",
                str(spec_path)
            ]
            
            result = subprocess.run(
                cmd,
                cwd=str(self.project_root),
                capture_output=True,
                text=True
            )
            
            if result.returncode != 0:
                self.logger.error(f"PyInstaller ошибка: {result.stderr}")
                return False
            
            self.logger.info("PyInstaller завершён успешно")
            return True
            
        except Exception as e:
            self.logger.error(f"Ошибка запуска PyInstaller: {e}")
            return False
    
    def _copy_resources(self, profile: str):
        """Копирование необходимых ресурсов"""
        # Копирование конфигураций
        config_src = self.project_root / "config"
        config_dst = self.output_dir / "config"
        
        if config_src.exists():
            if config_dst.exists():
                shutil.rmtree(config_dst)
            shutil.copytree(config_src, config_dst)
        
        # Для EXE версии - только нужные модели
        models_src = self.project_root / "models"
        models_dst = self.output_dir / "models"
        
        if models_src.exists():
            models_dst.mkdir(parents=True, exist_ok=True)
            
            if profile == "exe":
                # Копирование только дефолтной модели
                for model in models_src.glob("predictor_*.onnx"):
                    shutil.copy2(model, models_dst / model.name)
            else:
                shutil.copytree(models_src, models_dst, dirs_exist_ok=True)
        
        self.logger.debug("Ресурсы скопированы")
    
    def _verify_integrity(self, output_name: str) -> bool:
        """Проверка целостности сборки"""
        exe_path = self.output_dir / f"{output_name}.exe"
        
        if not exe_path.exists():
            self.logger.error(f"EXE файл не найден: {exe_path}")
            return False
        
        # Проверка размера (минимум 10MB для standalone)
        size_mb = exe_path.stat().st_size / (1024 * 1024)
        if size_mb < 10:
            self.logger.warning(f"Малый размер EXE: {size_mb:.1f}MB")
        
        self.logger.info(f"EXE создан: {size_mb:.1f}MB")
        return True
    
    def _create_manifest(self, profile: str, output_name: str):
        """Создание манифеста сборки"""
        manifest = {
            "name": output_name,
            "profile": profile,
            "version": "1.0.0",
            "build_date": datetime.now().isoformat(),
            "python_version": "3.x",
            "included_modules": self.include_modules,
            "excluded_modules": self.exclude_modules,
            "requirements": {
                "windows": "Windows 10+",
                "memory": "2GB RAM minimum",
                "gpu": "Optional (for CUDA acceleration)"
            }
        }
        
        manifest_path = self.output_dir / "manifest.json"
        with open(manifest_path, 'w', encoding='utf-8') as f:
            json.dump(manifest, f, indent=2, ensure_ascii=False)
        
        self.logger.info(f"Манифест создан: {manifest_path}")
    
    def get_build_info(self) -> Dict[str, Any]:
        """Получение информации о последней сборке"""
        manifest_path = self.output_dir / "manifest.json"
        
        if not manifest_path.exists():
            return {"status": "no_builds"}
        
        try:
            with open(manifest_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            self.logger.error(f"Ошибка чтения манифеста: {e}")
            return {"status": "error", "message": str(e)}
    
    def clean(self):
        """Очистка временных файлов сборки"""
        if self.build_dir.exists():
            shutil.rmtree(self.build_dir)
            self.logger.info("Build директория очищена")
        
        # Удаление spec файлов
        for spec in self.project_root.glob("*.spec"):
            spec.unlink()
        
        self.logger.info("Временные файлы удалены")
