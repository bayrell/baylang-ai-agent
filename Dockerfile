FROM python:3.12-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src/ ./src/

# Пользователь user (id 1000), домашняя папка /data/home
RUN mkdir -p /data \
    && useradd -m -u 1000 -d /data/home -s /bin/bash user \
    && git config --global user.name "BayLang Agent" \
    && git config --global user.email "agent@baylang.local" \
    && chown -R user:user /data/home

ENV HOME=/data/home
ENV PYTHONUNBUFFERED=1

USER user

# Foreground: опрос сервера и выполнение задач
CMD ["python", "src/main.py", "--foreground"]
