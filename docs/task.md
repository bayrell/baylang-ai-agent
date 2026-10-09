Используй библиотеку pyndantic AI чтобы разработать агента. Сохранять историю нужно в папке ~/.baylang/history/unixtimestamp.json. Промпт находится ~/.baylang/prompt.txt

from dotenv import find_dotenv, load_dotenv
from pydantic_core import to_jsonable_python
from pydantic_ai import Agent, RunContext, ModelRequest, ModelResponse, SystemPromptPart, UserPromptPart, TextPart
from pydantic_ai.models.openrouter import OpenRouterModel, OpenRouterModelSettings, OpenRouterProviderConfig
from pydantic_ai.providers.openrouter import OpenRouterProvider
from pydantic_ai.capabilites import LocalWorkSpace
from pydantic_ai_harness import FileSystem, RepoContext, Shell, ClearToolResults

APP_URL = "https://baylang.com/"
APP_TITLE = "BayLang AI"

load_dotenv(dotenv_path=find_dotenv(usecwd=True))

def build_agent(capabilities=None):
    
    if capabilities is None:
        capabilities = []
    
    config = OpenRouterProviderConfig()

    if os.environ.getenv("OPENROUTER_PROVIDERS"):
        items = os.environ.getenv("OPENROUTER_PROVIDERS").split(",")
        config["only"] = list(map(lambda s: s.strip(), items))

    model = OpenRouterModel(
        os.environ.getenv("OPENROUTER_MODEL"),
        provider=OpenRouterProvider(
            api_key=os.environ.getenv("OPENROUTER_API_KEY"),
            app_url=APP_URL,
            app_title=APP_TITLE,
        ),
        settings=OpenRouterModelSettings(
            openrouter_cache_instructions=True,
            openrouter_cache_messages=True,
            openrouter_cache_tool_definitions=True,
            openrouter_provider=config,
        )
    )

    agent = Agent(
        model,
        capabilities=capabilities,
    )
    
    return agent

def build_software_engineer(capabilities=None):
    if capabilities is None:
        capabilities = []
    
    capabilities.extend([
        LocalWorkSpace(working_dir=os.getcwd()),
        FileSystem(),
        RepoContext(),
        Shell(),
        ClearToolResults(
            keep_pairs=6,
            max_fraction=0.6,
            min_clear_tokens=20_000,
        )
    ])
    
    return build_agent(capabilities)

class AI:
    def __init__(self, agent):
        self.agent = agent
        self.history = []
        self.context = []
        self.id = ""
        self.file_name = ""
    
    def save(self):
        data = {
            "id": self.id
            "history": to_jsonable_python(self.history),
            "context": to_jsonable_python(self.context),
        }
        with (open(self.filename, "w")) as f:
            f.save(data)
    
    def add_prompt(self, prompt):
        self.context.append(
            ModelRequest(parts=[SystemPromptPart(prompt)])
        )
    
    async def send(self, user_message):
        self.history.append(
            ModelRequest(parts=[UserPromptPart(user_message)])
        )
        result = await self.agent.run(
            user_message, 
            message_history=self.context
        )
        self.histort.append(
            ModelResponse(parts=[TextPart(result.output)])
        )
        self.context = result.all_messages()
        return result.output
