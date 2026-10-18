В app.py добавить

from pydantic_ai import UsageLimits

await agent.run(message, usage_limits=UsageLimits(request_limit=None))

Поменять промпт в foreground.py на Прочитай и выполни задание из docs/task.md