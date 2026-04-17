# Rako Online PC Bot - Central Repository

## 📁 Структура проекта

```
├── src/                    # Исходный код
│   ├── core/              # Ядро-оркестратор
│   ├── bot/               # Логика бота
│   ├── training/          # Модуль обучения нейросети
│   ├── screenshotter/     # Скриншотер и сортировщик
│   ├── bluestacks/        # Авто-установщик и конфигуратор
│   └── gui/               # Графический интерфейс
├── data/                   # Данные (не загружаются в Git)
│   ├── raw/               # Сырые скриншоты
│   ├── labeled/           # Размеченные данные
│   └── rejected/          # Брак
├── models/                 # Обученные модели (.onnx)
├── build/                  # Файлы сборки
├── tests/                  # Тесты
├── configs/                # Конфигурационные файлы
├── .gitignore             # Игнорируемые файлы
├── requirements.txt       # Зависимости Python
├── setup.py               # Настройки установки
└── README.md              # Документация
```

## 🚀 Быстрый старт

### 1. Установка зависимостей
```bash
pip install -r requirements.txt
```

### 2. Запуск бота
```bash
python src/core/orchestrator.py
```

### 3. Обучение модели
```bash
python src/training/trainer.py --data data/labeled --output models/model.onnx
```

### 4. Сборка .exe
```bash
python build/build_exe.py
```

## 📦 Модули

### 1. Оркестратор (`src/core/orchestrator.py`)
Центральное ядро, координирующее все компоненты системы.

### 2. Бот (`src/bot/`)
Основная логика игры: обнаружение мобов, атака, навигация.

### 3. Тренеровщик (`src/training/`)
Обучение YOLO-модели для распознавания мобов.

### 4. Скриншотер (`src/screenshotter/`)
Автоматические скриншоты из BlueStacks с сортировкой.

### 5. BlueStacks Manager (`src/bluestacks/`)
Установка, настройка и управление эмулятором.

### 6. GUI (`src/gui/`)
Графический интерфейс с панелью управления и визуализацией.

## ⚙️ Конфигурация

Все настройки хранятся в `configs/config.yaml`:
- Параметры подключения к BlueStacks
- Настройки нейросети
- Параметры бота (задержки, чувствительность)

## 🛠️ Сборка

Для создания .exe файла используется PyInstaller:
```bash
pyinstaller --onefile --windowed src/gui/main.py
```

## 📝 Лицензия

Проект создан для образовательных целей.