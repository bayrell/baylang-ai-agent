#!/bin/bash
# Настраивает git user.name / user.email из переменных окружения
# GIT_USER_NAME / GIT_USER_EMAIL (если заданы) и запускает main.py.
set -e

DIR="$(cd "$(dirname "$0")" && pwd)"

if [ -n "$GIT_USER_NAME" ]; then
    git config --global user.name "$GIT_USER_NAME"
fi
if [ -n "$GIT_USER_EMAIL" ]; then
    git config --global user.email "$GIT_USER_EMAIL"
fi

interval=${POOL_INTERVAL:-300}

while true; do
    python3 "$DIR/main.py" "$@"
    sleep interval
done
