"""
Графический интерфейс бота (GUI) на PyQt5
Панель управления, визуализация, логи
"""

import sys
import logging
from pathlib import Path
from typing import Optional
from datetime import datetime

from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QTextEdit, QGroupBox, QSpinBox, QDoubleSpinBox,
    QComboBox, QCheckBox, QSplitter, QFrame, QStatusBar, QMenuBar,
    QMenu, QAction, QFileDialog, QMessageBox
)
from PyQt5.QtCore import Qt, QTimer, pyqtSignal, QThread
from PyQt5.QtGui import QImage, QPixmap, QFont


class LogHandler(logging.Handler):
    """Обработчик логов для вывода в GUI"""
    
    def __init__(self, callback):
        super().__init__()
        self.callback = callback
    
    def emit(self, record):
        msg = self.format(record)
        self.callback(msg)


class VisualizationWidget(QLabel):
    """Виджет для отображения кадра с детекцией"""
    
    def __init__(self):
        super().__init__()
        self.setMinimumSize(640, 360)
        self.setStyleSheet("background-color: #1a1a1a; border: 2px solid #333;")
        self.setAlignment(Qt.AlignCenter)
        self.setText("Нет сигнала")
        self.setStyleSheet("""
            QLabel {
                background-color: #1a1a1a;
                border: 2px solid #333;
                color: #666;
                font-size: 18px;
            }
        """)
    
    def update_frame(self, image_data: bytes):
        """Обновление кадра"""
        if not image_data:
            return
        
        pixmap = QPixmap()
        if pixmap.loadFromData(image_data):
            scaled = pixmap.scaled(
                self.size(), 
                Qt.KeepAspectRatio,
                Qt.SmoothTransformation
            )
            self.setPixmap(scaled)
            self.setText("")


class MainWindow(QMainWindow):
    """Главное окно приложения"""
    
    # Сигналы для связи с потоками
    log_signal = pyqtSignal(str)
    frame_signal = pyqtSignal(bytes)
    
    def __init__(self, config: dict, orchestrator=None):
        super().__init__()
        
        self.config = config
        self.orchestrator = orchestrator
        self.is_running = False
        
        self.setWindowTitle("Rako Online Bot - Панель управления")
        self.setMinimumSize(1200, 800)
        
        # Настройка UI
        self._init_ui()
        self._init_menu()
        self._init_status_bar()
        
        # Настройка логирования
        self._setup_logging()
        
        # Таймер обновления
        self.update_timer = QTimer()
        self.update_timer.timeout.connect(self._on_update_timer)
        self.update_timer.start(1000)  # Обновление каждую секунду
    
    def _init_ui(self):
        """Инициализация интерфейса"""
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        main_layout = QHBoxLayout(central_widget)
        
        # Левая панель - управление
        left_panel = self._create_control_panel()
        
        # Центральная часть - визуализация
        center_panel = self._create_visualization_panel()
        
        # Правая панель - логи и статистика
        right_panel = self._create_log_panel()
        
        # Разделитель
        splitter = QSplitter(Qt.Horizontal)
        splitter.addWidget(left_panel)
        splitter.addWidget(center_panel)
        splitter.addWidget(right_panel)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 3)
        splitter.setStretchFactor(2, 2)
        
        main_layout.addWidget(splitter)
    
    def _create_control_panel(self) -> QGroupBox:
        """Панель управления"""
        group = QGroupBox("Управление")
        layout = QVBoxLayout(group)
        
        # Кнопки старт/стоп
        self.start_btn = QPushButton("▶ ЗАПУСК")
        self.start_btn.setFixedHeight(50)
        self.start_btn.setStyleSheet("""
            QPushButton {
                background-color: #27ae60;
                color: white;
                font-size: 16px;
                font-weight: bold;
                border-radius: 5px;
            }
            QPushButton:hover {
                background-color: #2ecc71;
            }
            QPushButton:disabled {
                background-color: #555;
            }
        """)
        self.start_btn.clicked.connect(self._on_start_clicked)
        
        self.stop_btn = QPushButton("⏹ СТОП")
        self.stop_btn.setFixedHeight(50)
        self.stop_btn.setStyleSheet("""
            QPushButton {
                background-color: #c0392b;
                color: white;
                font-size: 16px;
                font-weight: bold;
                border-radius: 5px;
            }
            QPushButton:hover {
                background-color: #e74c3c;
            }
            QPushButton:disabled {
                background-color: #555;
            }
        """)
        self.stop_btn.clicked.connect(self._on_stop_clicked)
        self.stop_btn.setEnabled(False)
        
        layout.addWidget(self.start_btn)
        layout.addWidget(self.stop_btn)
        
        layout.addSpacing(20)
        
        # Режим работы
        mode_group = QGroupBox("Режим работы")
        mode_layout = QVBoxLayout(mode_group)
        
        self.mode_combo = QComboBox()
        self.mode_combo.addItems(["Авто", "Фарм", "Ручной"])
        mode_layout.addWidget(self.mode_combo)
        
        layout.addWidget(mode_group)
        
        # Настройки
        settings_group = QGroupBox("Настройки")
        settings_layout = QVBoxLayout(settings_group)
        
        # Чувствительность
        sens_layout = QHBoxLayout()
        sens_layout.addWidget(QLabel("Чувствительность:"))
        self.sensitivity_spin = QDoubleSpinBox()
        self.sensitivity_spin.setRange(0.1, 1.0)
        self.sensitivity_spin.setValue(0.6)
        self.sensitivity_spin.setSingleStep(0.05)
        sens_layout.addWidget(self.sensitivity_spin)
        settings_layout.addLayout(sens_layout)
        
        # Задержка
        delay_layout = QHBoxLayout()
        delay_layout.addWidget(QLabel("Задержка (мс):"))
        self.delay_spin = QSpinBox()
        self.delay_spin.setRange(50, 1000)
        self.delay_spin.setValue(100)
        self.delay_spin.setSingleStep(50)
        delay_layout.addWidget(self.delay_spin)
        settings_layout.addLayout(delay_layout)
        
        layout.addWidget(settings_group)
        
        # Статус подключения
        status_group = QGroupBox("Статус")
        status_layout = QVBoxLayout(status_group)
        
        self.bs_status = QLabel("BlueStacks: ❌")
        self.bs_status.setStyleSheet("color: #e74c3c;")
        status_layout.addWidget(self.bs_status)
        
        self.bot_status = QLabel("Бот: ❌")
        self.bot_status.setStyleSheet("color: #e74c3c;")
        status_layout.addWidget(self.bot_status)
        
        self.model_status = QLabel("Модель: ❌")
        self.model_status.setStyleSheet("color: #e74c3c;")
        status_layout.addWidget(self.model_status)
        
        layout.addWidget(status_group)
        
        layout.addStretch()
        
        return group
    
    def _create_visualization_panel(self) -> QGroupBox:
        """Панель визуализации"""
        group = QGroupBox("Визуализация")
        layout = QVBoxLayout(group)
        
        self.visualization = VisualizationWidget()
        layout.addWidget(self.visualization)
        
        # Инфо панель
        info_layout = QHBoxLayout()
        
        self.fps_label = QLabel("FPS: 0")
        info_layout.addWidget(self.fps_label)
        
        self.mobs_label = QLabel("Мобы: 0")
        info_layout.addWidget(self.mobs_label)
        
        info_layout.addStretch()
        
        self.resolution_label = QLabel("1920x1080")
        info_layout.addWidget(self.resolution_label)
        
        layout.addLayout(info_layout)
        
        return group
    
    def _create_log_panel(self) -> QGroupBox:
        """Панель логов"""
        group = QGroupBox("События")
        layout = QVBoxLayout(group)
        
        # Текстовое поле логов
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setFont(QFont("Consolas", 9))
        self.log_text.setStyleSheet("""
            QTextEdit {
                background-color: #0d0d0d;
                color: #0f0;
                border: 1px solid #333;
            }
        """)
        layout.addWidget(self.log_text)
        
        # Кнопки управления логами
        btn_layout = QHBoxLayout()
        
        clear_btn = QPushButton("Очистить")
        clear_btn.clicked.connect(self.log_text.clear)
        btn_layout.addWidget(clear_btn)
        
        save_btn = QPushButton("Сохранить")
        save_btn.clicked.connect(self._save_logs)
        btn_layout.addWidget(save_btn)
        
        btn_layout.addStretch()
        
        layout.addLayout(btn_layout)
        
        return group
    
    def _init_menu(self):
        """Инициализация меню"""
        menubar = self.menuBar()
        
        # Файл
        file_menu = menubar.addMenu("Файл")
        
        load_model_action = QAction("Загрузить модель...", self)
        load_model_action.triggered.connect(self._load_model)
        file_menu.addAction(load_model_action)
        
        file_menu.addSeparator()
        
        exit_action = QAction("Выход", self)
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)
        
        # Настройки
        settings_menu = menubar.addMenu("Настройки")
        
        config_action = QAction("Конфигурация...", self)
        config_action.triggered.connect(self._open_config)
        settings_menu.addAction(config_action)
        
        # Помощь
        help_menu = menubar.addMenu("Помощь")
        
        about_action = QAction("О программе", self)
        about_action.triggered.connect(self._show_about)
        help_menu.addAction(about_action)
    
    def _init_status_bar(self):
        """Инициализация статусной строки"""
        self.statusbar = QStatusBar()
        self.setStatusBar(self.statusbar)
        self.statusbar.showMessage("Готов к работе")
    
    def _setup_logging(self):
        """Настройка логирования"""
        self.log_handler = LogHandler(self._append_log)
        self.log_handler.setLevel(logging.INFO)
        
        formatter = logging.Formatter(
            '%(asctime)s - %(levelname)s - %(message)s',
            datefmt='%H:%M:%S'
        )
        self.log_handler.setFormatter(formatter)
        
        logger = logging.getLogger()
        logger.addHandler(self.log_handler)
    
    def _append_log(self, message: str):
        """Добавление сообщения в лог"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.log_text.append(f"[{timestamp}] {message}")
        self.log_text.verticalScrollBar().setValue(
            self.log_text.verticalScrollBar().maximum()
        )
    
    def _on_start_clicked(self):
        """Обработчик кнопки запуска"""
        self.log_message("Запуск системы...")
        
        if self.orchestrator:
            success = self.orchestrator.start()
            if success:
                self.is_running = True
                self.start_btn.setEnabled(False)
                self.stop_btn.setEnabled(True)
                self._update_status_indicators(True)
                self.statusbar.showMessage("Система запущена")
            else:
                self.log_message("❌ Ошибка запуска!")
                QMessageBox.critical(self, "Ошибка", "Не удалось запустить систему")
        else:
            # Демонстрационный режим
            self.is_running = True
            self.start_btn.setEnabled(False)
            self.stop_btn.setEnabled(True)
            self._update_status_indicators(True)
            self.log_message("✅ Система запущена (демо-режим)")
    
    def _on_stop_clicked(self):
        """Обработчик кнопки остановки"""
        self.log_message("Остановка системы...")
        
        if self.orchestrator:
            self.orchestrator.stop()
        
        self.is_running = False
        self.start_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self._update_status_indicators(False)
        self.statusbar.showMessage("Система остановлена")
        self.log_message("✅ Система остановлена")
    
    def _update_status_indicators(self, running: bool):
        """Обновление индикаторов статуса"""
        color = "#27ae60" if running else "#e74c3c"
        status = "✅" if running else "❌"
        
        self.bs_status.setStyleSheet(f"color: {color};")
        self.bs_status.setText(f"BlueStacks: {status}")
        
        self.bot_status.setStyleSheet(f"color: {color};")
        self.bot_status.setText(f"Бот: {status}")
    
    def _on_update_timer(self):
        """Таймер обновления статуса"""
        if self.is_running and self.orchestrator:
            status = self.orchestrator.get_status()
            
            # Обновление FPS (заглушка)
            import random
            fps = random.randint(25, 35)
            self.fps_label.setText(f"FPS: {fps}")
    
    def log_message(self, message: str):
        """Логирование сообщения"""
        self._append_log(message)
    
    def update_visualization(self, frame_bytes: bytes):
        """Обновление кадра визуализации"""
        self.visualization.update_frame(frame_bytes)
    
    def _save_logs(self):
        """Сохранение логов в файл"""
        filename, _ = QFileDialog.getSaveFileName(
            self, "Сохранить логи", "", "Text Files (*.txt)"
        )
        
        if filename:
            with open(filename, 'w', encoding='utf-8') as f:
                f.write(self.log_text.toPlainText())
            self.log_message(f"Логи сохранены: {filename}")
    
    def _load_model(self):
        """Загрузка модели"""
        filename, _ = QFileDialog.getOpenFileName(
            self, "Загрузить модель", "", "ONNX Files (*.onnx)"
        )
        
        if filename:
            self.log_message(f"Модель загружена: {filename}")
            self.model_status.setText("Модель: ✅")
            self.model_status.setStyleSheet("color: #27ae60;")
    
    def _open_config(self):
        """Открытие конфигурации"""
        self.log_message("Открытие конфигурации...")
    
    def _show_about(self):
        """О программе"""
        QMessageBox.about(
            self,
            "О программе",
            "<h2>Rako Online Bot</h2>"
            "<p>Версия: 1.0.0</p>"
            "<p>Автоматизация игры Rako Online</p>"
            "<p>© 2024</p>"
        )
    
    def closeEvent(self, event):
        """Обработчик закрытия окна"""
        if self.is_running:
            reply = QMessageBox.question(
                self, 'Подтверждение',
                'Система работает. Остановить?',
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No
            )
            
            if reply == QMessageBox.Yes:
                if self.orchestrator:
                    self.orchestrator.stop()
                event.accept()
            else:
                event.ignore()
        else:
            event.accept()


def run_gui(config: dict, orchestrator=None):
    """Запуск GUI приложения"""
    app = QApplication(sys.argv)
    
    # Стиль приложения
    app.setStyle('Fusion')
    
    window = MainWindow(config, orchestrator)
    window.show()
    
    sys.exit(app.exec_())


if __name__ == "__main__":
    # Загрузка конфига для тестирования
    from configs.config_loader import ConfigLoader
    config = ConfigLoader.load()
    
    run_gui(config)
