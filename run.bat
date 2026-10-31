@echo off
chcp 65001 >nul
rem Проверка цен по расписанию двойным кликом. Пока окно открыто — проверки идут.
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo Не найдено окружение .venv. Создай его командами из README:
    echo   py -V:3.14 -m venv .venv
    echo   .venv\Scripts\python -m pip install -r requirements.txt
    pause
    exit /b 1
)
if not exist ".env" (
    echo Не найден файл .env. Скопируй .env.example в .env и заполни его.
    pause
    exit /b 1
)

title Price Sheet
".venv\Scripts\python.exe" -m app.watch
echo.
echo Остановлено.
pause
