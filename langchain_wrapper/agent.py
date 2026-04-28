"""
Agent 封装
提供支持外部工具调用（如搜索）的 Agent
"""

from langchain.agents import AgentType, initialize_agent
from langchain_community.tools import DuckDuckGoSearchRun
from langchain_core.language_models import BaseChatModel


def create_search_agent(model: BaseChatModel, verbose: bool = True):
  """
  创建一个带有 DuckDuckGo 搜索工具的 Agent。
  使用 CHAT_ZERO_SHOT_REACT_DESCRIPTION 可以在聊天模型下运行 ReACT 逻辑。
  """
  tools = [DuckDuckGoSearchRun()]
  
  # 注意：在较新的 langchain 版本中，可以使用 create_react_agent 与 AgentExecutor，
  # 为了兼容性和简单性，这里使用 initialize_agent。
  agent = initialize_agent(
    tools=tools,
    llm=model,
    agent=AgentType.CHAT_ZERO_SHOT_REACT_DESCRIPTION,
    verbose=verbose,
    handle_parsing_errors=True,
  )
  
  return agent
