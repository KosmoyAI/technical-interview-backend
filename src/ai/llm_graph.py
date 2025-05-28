from __future__ import annotations

import ast
import operator as op
from typing import Iterator, List, TypedDict, Literal

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

def agent_node(state: AgentState) -> AgentState:
    """Main agent node that calls the LLM."""
    response: AIMessage = agent_llm.invoke(state["messages"])
    return {"messages": state["messages"] + [response]}


def should_continue(state: AgentState) -> Literal["tools", "__end__"]:
    """Determine whether to continue to tools or end."""
    messages = state["messages"]
    last_message = messages[-1]
    
    # If the LLM makes a tool call, then we route to the "tools" node
    if isinstance(last_message, AIMessage) and last_message.tool_calls:
        return "tools"
    # Otherwise, we stop (reply to the user)
    return "__end__"


def tool_node(state: AgentState) -> AgentState:
    """Execute tool calls and return the results."""
    messages = state["messages"]
    last_message = messages[-1]
    
    if not isinstance(last_message, AIMessage) or not last_message.tool_calls:
        raise ValueError("Expected AIMessage with tool_calls")
    
    tool_messages = []
    for tool_call in last_message.tool_calls:
        if tool_call["name"] == "calculate":
            try:
                # Extract the expression argument
                args = tool_call["args"]
                result = calculate(args["expression"])
                
                tool_msg = ToolMessage(
                    content=result,
                    tool_call_id=tool_call["id"],
                )
            except Exception as e:
                tool_msg = ToolMessage(
                    content=f"Error: {str(e)}",
                    tool_call_id=tool_call["id"],
                )
        else:
            tool_msg = ToolMessage(
                content=f"Unknown tool: {tool_call['name']}",
                tool_call_id=tool_call["id"],
            )
        
        tool_messages.append(tool_msg)
    
    return {"messages": messages + tool_messages}


# Create the graph
workflow = StateGraph(AgentState)

# Add nodes
workflow.add_node("agent", agent_node)
workflow.add_node("tools", tool_node)

# Set the entrypoint
workflow.set_entry_point("agent")

# Add conditional edges
workflow.add_conditional_edges(
    "agent",
    should_continue,
)

# Add normal edge from tools back to agent
workflow.add_edge("tools", "agent")

# Compile the workflow
executor = workflow.compile()

# ---------------------------------------------------------------------------
# Convenience helpers
# ---------------------------------------------------------------------------

def run_llm(prompt: str) -> str:
    """Blocking one‑shot call."""
    state = executor.invoke({"messages": [HumanMessage(content=prompt)]})
    for msg in reversed(state["messages"]):
        if isinstance(msg, AIMessage):
            return msg.content or ""
    raise RuntimeError("Agent produced no AIMessage")


def stream_llm(prompt: str) -> Iterator[str]:
    """Yield partial completions as they stream back from the model."""
    for event in executor.stream({"messages": [HumanMessage(content=prompt)]}):
        for node_name, node_output in event.items():
            if "messages" in node_output:
                last = node_output["messages"][-1]
                if isinstance(last, AIMessage) and last.content:
                    yield last.content
