from mcp_tools_rag.common.llm_services import get_llm, get_analyze_llm
from langgraph.graph import StateGraph
from mcp_tools_rag.nodes.analyze_node import analyze_node
from mcp_tools_rag.nodes.retrieve_node import retrieve_node
from mcp_tools_rag.nodes.agent_node import agent_node
from mcp_tools_rag.nodes.validate_node import validate_node
from mcp_tools_rag.nodes.execute_node import execute_node
from mcp_tools_rag.common.state import AgentState
from langgraph.types import Command
from langchain_core.runnables import RunnableConfig
from typing import Literal

# 工厂函数包装
def make_agent_node(llm):
    async def node(
        state: AgentState,
        config: RunnableConfig,
    ) -> Command[Literal['validate', '__end__']]:
        return await agent_node(state, llm, config)

    return node

def make_analyze_node(llm):
    async def node(
        state: AgentState,
    ) -> Command[Literal['retrieve', 'agent']]:
        return await analyze_node(state, llm)

    return node

async def build_graph(checkpointer):

    graph = (
        StateGraph(AgentState)
        .add_node("analyze", make_analyze_node(get_analyze_llm()))
        .add_node("retrieve", retrieve_node)
        .add_node("agent", make_agent_node(get_llm()))
        .add_node("validate", validate_node)
        .add_node("tools", execute_node)

        .add_edge("__start__", "analyze")

        .compile(checkpointer=checkpointer)

    )

    return graph
