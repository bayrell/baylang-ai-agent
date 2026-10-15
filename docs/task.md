Добавить tools git diff для AI просмотр изменений текущей ветки по отношению к main или master. Если нужно код ревью фичи, то полезно выполнить эту команду, чтобы узнать список изменений, которые были сделаны.

Пример:
from pydantic_ai.capabilities import AbstractCapability
from pydantic_ai.toolsets import AgentToolset, FunctionToolset
math_toolset = FunctionToolset()
@math_toolset.tool_plain
def add(a: float, b: float) -> float:
    """Add two numbers."""
    return a + b
@math_toolset.tool_plain
def multiply(a: float, b: float) -> float:
    """Multiply two numbers."""
    return a * b
@dataclass
class MathTools(AbstractCapability[Any]):
    """Provides basic math operations."""
    def get_toolset(self) -> AgentToolset[Any] | None:
        return math_toolset