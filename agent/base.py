from typing import Annotated, Sequence, TypedDict, List
import json
from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages
from langchain_core.messages import ToolMessage, SystemMessage, HumanMessage
from langchain_core.runnables import RunnableConfig
from langgraph.graph import StateGraph, END
from langchain_core.tools import BaseTool
from langchain_core.language_models.chat_models import BaseChatModel
from langgraph.checkpoint.memory import MemorySaver
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_anthropic import ChatAnthropic


class TokenCallbackHandler:
    def __init__(self):
        self.total_input_token = 0
        self.total_output_token = 0

    def update_total_tokens(self, input_token: int, output_token: int):
        self.total_input_token += input_token
        self.total_output_token += output_token

    def get_tokens(self):
        return self.total_input_token, self.total_output_token


class AgentState(TypedDict):
    """The state of the agent."""

    messages: Annotated[Sequence[BaseMessage], add_messages]
    history_token: int
    input_token: int
    output_token: int


class PhiAgent:
    def __init__(
        self,
        llm: BaseChatModel,
        tools: List[BaseTool],
        system_prompt: str,
    ):
        self.token_callback_handler = TokenCallbackHandler()
        self.state_graph = StateGraph(input=AgentState, output=AgentState)
        self.tools_by_name = {tool.name: tool for tool in tools}
        self.llm_with_tools = llm.bind_tools(tools)
        self.memory = MemorySaver()
        self.setup_nodes()
        self.setup_edges()

        if isinstance(llm, ChatGoogleGenerativeAI):
            self.system_prompt = HumanMessage(system_prompt)
        else:
            self.system_prompt = SystemMessage(system_prompt)

        if isinstance(llm, ChatGoogleGenerativeAI):
            self.provider = "google"
        elif isinstance(llm, ChatAnthropic):
            self.provider = "anthropic"
        else:
            self.provider = "openai"

    def setup_nodes(self):
        self.state_graph.add_node("agent", self.call_model)
        self.state_graph.add_node("tools", self.tool_node)

    def setup_edges(self):
        self.state_graph.set_entry_point("agent")
        self.state_graph.add_conditional_edges(
            "agent",
            self.should_continue,
            {
                "continue": "tools",
                "end": END,
            },
        )
        self.state_graph.add_edge("tools", "agent")

    async def tool_node(self, state: AgentState):
        outputs = []

        for tool_call in state["messages"][-1].tool_calls:
            tool_result = await self.tools_by_name[tool_call["name"]].ainvoke(
                tool_call["args"],
            )
            content = json.dumps(tool_result)
            outputs.append(
                ToolMessage(
                    content=content[:30000],
                    name=tool_call["name"],
                    tool_call_id=tool_call["id"],
                )
            )

        return {"messages": outputs}

    def extract_token_metadata(self, response):
        if self.provider == "google":
            usage = response.usage_metadata
            input_token = usage.get("input_tokens", 0)
            output_token = usage.get("output_tokens", 0)

        elif self.provider == "anthropic":
            usage = response.usage_metadata
            input_token = usage.get("input_tokens", 0)
            output_token = usage.get("output_tokens", 0)

        elif self.provider == "openai":
            usage = response.usage_metadata
            input_token = usage.get("input_tokens", 0)
            output_token = usage.get("output_tokens", 0)

        return input_token, output_token

    async def call_model(self, state: AgentState, config: RunnableConfig):
        response = await self.llm_with_tools.ainvoke(
            [self.system_prompt] + state["messages"],
            config=config,
        )

        input_token, output_token = self.extract_token_metadata(response)
        # print(str(response.__dict__))

        # Update sum of token
        self.token_callback_handler.update_total_tokens(input_token, output_token)
        return {
            "messages": [response],
            "input_token": input_token,
            "output_token": output_token,
        }

    def should_continue(self, state: AgentState):
        messages = state["messages"]
        last_message = messages[-1]
        return "end" if not last_message.tool_calls else "continue"

    def compile(self):
        compiler = self.state_graph.compile(checkpointer=self.memory)
        compiler.token_callback_handler = self.token_callback_handler
        return compiler


if __name__ == "__main__":
    agent_instance = PhiAgent()
    agent_graph = agent_instance.compile()
