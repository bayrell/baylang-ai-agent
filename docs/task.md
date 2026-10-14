Добавить AGENTS.md в проект и обновить readme список env для запуска и настройки системы

Пример запуска Docker
docker stop baylang_agent
docker rm baylang_agent

docker run -d \
    --env OPENROUTER_API_KEY="" \
    --env OPENROUTER_MODEL="openrouter/auto" \
    --env TZ="Asia/Almaty" \
    --name baylang_agent \
    -v ./baylang:/data/home \
    -v ./project:/data/home/project \
    bayrell/baylang-ai-agent:1.0.0