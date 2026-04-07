from main import app
from langchain_openai import ChatOpenAI
from langchain.agents import initialize_agent, AgentType


class AgentClient:

    def __init__(self):
        self.llm = ChatOpenAI(
            model=app.config["LLM_MODEL"],
            temperature=app.config["LLM_TEMPERATURE"],
            api_key=app.config["LLM_API_KEY"],
            base_url=app.config["LLM_BASE_URL"],
        )

        tools = []

        self.agent = initialize_agent(
            tools=tools,
            llm=self.llm,
            agent=AgentType.OPENAI_FUNCTIONS,
            verbose=True,
        )

    def analyse_poll_secends():
        pass

    def analyse_dump_core():
        pass


agent = AgentClient()