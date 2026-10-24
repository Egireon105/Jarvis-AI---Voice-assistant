@echo off
chcp 65001 >nul
echo ============================================
echo   Установка и запуск Jarvis (Python 3.12)
echo ============================================

:: Проверяем наличие Python 3.12 через лаунчер Windows (py)
py -3.12 --version >nul 2>&1
if errorlevel 1 (
    echo [WARN] Python 3.12 не найден. Пытаюсь установить через winget...
    winget install Python.Python.3.12 --accept-source-agreements --accept-package-agreements
    py -3.12 --version >nul 2>&1
    if errorlevel 1 (
        echo [ERR] Не удалось установить Python 3.12. Установите его вручную.
        pause
        exit /b 1
    )
)

:: Создаём виртуальное окружение СТРОГО на Python 3.12
if not exist .venv (
    echo Создаю виртуальное окружение на Python 3.12...
    py -3.12 -m venv .venv
)

:: Активируем и обновляем pip
call .venv\Scripts\activate.bat
python -m pip install --upgrade pip >nul

:: Устанавливаем зависимости
echo Устанавливаю зависимости...
pip install vosk sounddevice numpy pycaw comtypes

:: Проверяем модель Vosk
if not exist vosk-model-small-ru-0.22 (
    echo [WARN] Модель Vosk не найдена. Распакуй архив vosk-model-small-ru-0.22 в папку C:\Jarvis\
)

echo.
echo ============================================
echo   Запуск Jarvis
echo ============================================
python Jarvis.py
pause