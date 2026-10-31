# Рецепт «коробки» с мониторингом цен: Python + Google Chrome + виртуальный экран
FROM python:3.13-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Сначала только зависимости: Docker запомнит этот слой, и при изменении
# кода библиотеки и Chrome не будут скачиваться заново
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
    # Google Chrome со всеми системными библиотеками — для защищённых сайтов (DNS, WB, Ozon)
    && patchright install --with-deps chrome \
    # Виртуальный экран: Chrome запускается «с окном» (так его реже принимают за бота),
    # а на сервере монитора нет — окно рисуется в памяти
    && apt-get update && apt-get install -y --no-install-recommends xvfb xauth \
    && rm -rf /var/lib/apt/lists/*

COPY app/ ./app/

# xvfb-run создаёт виртуальный экран и запускает проверку по расписанию
CMD ["xvfb-run", "-a", "--server-args=-screen 0 1366x900x24", "python", "-m", "app.watch"]
