FROM python:3.12-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends git openssh-client \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY README.md ./
COPY src/ ./
RUN chmod +x run.sh

# Пользователь user (id 1000), домашняя папка /data/home
# git user.name/user.email задаются при запуске контейнера
# через GIT_USER_NAME / GIT_USER_EMAIL (см. run.sh)
RUN mkdir -p /data \
    && useradd -m -u 1000 -d /data/home -s /bin/bash user \
    && chown -R user:user /data/home

ENV HOME=/data/home
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV PATH="/data/home/bin:${PATH}"

USER user

# Foreground: опрос сервера и выполнение задач
# (run.sh настраивает git user из GIT_USER_NAME / GIT_USER_EMAIL, если заданы)
CMD ["/app/run.sh", "--foreground"]
