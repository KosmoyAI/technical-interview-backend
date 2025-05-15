from __future__ import annotations

import ast
import json
import operator as op
from typing import Iterator, List, TypedDict

from langchain_openai import ChatOpenAI
from langgraph.graph import StateGraph, END
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, ToolMessage

from ..utils.env import get_settings

settings = get_settings()

# ---------------------------------------------------------------------------
# Agent state held by LangGraph
# ---------------------------------------------------------------------------

class AgentState(TypedDict):
    messages: List[BaseMessage]

# ---------------------------------------------------------------------------
# Calculator tool
# ---------------------------------------------------------------------------

_ALLOWED = {
    ast.Add: op.add,
    ast.Sub: op.sub,
    ast.Mult: op.mul,
    ast.Div: op.truediv,
    ast.Pow: op.pow,
    ast.USub: op.neg,
}


def _safe(node: ast.AST):
    """Evaluate supported arithmetic AST nodes only."""
    if isinstance(node, (ast.Num, ast.Constant)):  # py≤3.7 uses ast.Num
        value = getattr(node, "n", getattr(node, "value", None))
        if not isinstance(value, (int, float)):
            raise ValueError("Only int/float literals are allowed")
        return value

    if isinstance(node, ast.UnaryOp) and type(node.op) in _ALLOWED:
        return _ALLOWED[type(node.op)](_safe(node.operand))

    if isinstance(node, ast.BinOp) and type(node.op) in _ALLOWED:
        return _ALLOWED[type(node.op)](_safe(node.left), _safe(node.right))

    raise ValueError("Unsupported expression, allowed ops: + - * / ** and unary -")


def calculate(expression: str) -> str:
    """Safely evaluate a basic arithmetic *expression* and return the result."""
    return str(_safe(ast.parse(expression, mode="eval").body))

# ---------------------------------------------------------------------------
# Large‑language model (via OpenRouter) with the tool bound once
# ---------------------------------------------------------------------------

agent_llm = ChatOpenAI(
    model=settings.OPENROUTER_MODEL,
    api_key=settings.OPENROUTER_API_KEY,
    base_url=settings.OPENROUTER_BASE_URL,
    temperature=0.7,
    default_headers={  # optional but recommended by OpenRouter
        "HTTP-Referer": settings.YOUR_SITE_URL,
        "X-Title": settings.YOUR_SITE_NAME,
    },
)

# Expose the calculator to the model.  LangChain converts the signature+docstring
# into the JSON schema required by the OpenAI tools API.
agent_llm = agent_llm.bind_tools([calculate])

# ---------------------------------------------------------------------------
# LangGraph setup
# ---------------------------------------------------------------------------

graph = StateGraph(AgentState)


def agent_node(state: AgentState) -> AgentState:
    response: AIMessage = agent_llm.invoke(state["messages"])
    return {"messages": state["messages"] + [response]}


graph.add_node("agent", agent_node)


def router(state: AgentState) -> str:
    last = state["messages"][-1]
    if isinstance(last, AIMessage) and getattr(last, "tool_calls", []):
        return "calculator"
    return END


graph.add_node("router", router)

graph.add_edge("agent", "router")


def calculator_node(state: AgentState) -> AgentState:
    last: AIMessage = state["messages"][-1]
    call = last.tool_calls[0]

    args = json.loads(call["function"]["arguments"] or "{}")
    result = calculate(**args)  # **args → expression=str

    tool_msg = ToolMessage(
        content=result,
        tool_call_id=call["id"],
        name=call["function"]["name"],  # not strictly required but useful
    )
    return {"messages": state["messages"] + [tool_msg]}


graph.add_node("calculator", calculator_node)

graph.add_edge("calculator", "agent")

# Where execution starts
graph.set_entry_point("agent")
executor = graph.compile()

# ---------------------------------------------------------------------------
# Convenience helpers
# ---------------------------------------------------------------------------

def run_llm(prompt: str) -> str:
    """Blocking one‑shot call."""
    state = executor.invoke({"messages": [HumanMessage(content=prompt)]})
    for msg in reversed(state["messages"]):
        if isinstance(msg, AIMessage):
            return msg.content
    raise RuntimeError("Agent produced no AIMessage")


def stream_llm(prompt: str) -> Iterator[str]:
    """Yield partial completions as they stream back from the model."""
    for update in executor.stream({"messages": [HumanMessage(content=prompt)]}):
        if "messages" in update:
            last = update["messages"][-1]
            if isinstance(last, AIMessage):
                yield last.content

