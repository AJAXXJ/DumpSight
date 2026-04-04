from main import app
from langchain_openai import ChatOpenAI


class AgentClient:

    def __init__(self):
        self.llm = ChatOpenAI(
            model=app.config["LLM_MODEL"],
            temperature=app.config["LLM_TEMPERATURE"],
            api_key=app.config["LLM_API_KEY"],
            base_url=app.config["LLM_BASE_URL"],
        )

        
