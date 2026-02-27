# Telegram Planning Bot (Atkinternal)
# Сборка из корня репозитория: docker build -t telegram-planning-bot .

FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Код копируем в bot/, чтобы работало: python -m bot
COPY . ./bot/

CMD ["python", "-m", "bot"]
