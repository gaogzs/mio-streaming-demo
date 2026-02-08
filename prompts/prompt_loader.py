"""
提示词加载器
负责加载和组合提示词文件
"""

from pathlib import Path
from typing import Optional


class PromptLoader:
  """
  提示词加载器类
  用于加载基础指令和人设提示词
  """

  # 支持的人设名称
  PERSONAS = ["mio", "sage", "kuro"]

  def __init__(self, prompts_dir: Optional[Path] = None):
    """
    初始化提示词加载器

    Args:
      prompts_dir: 提示词文件所在目录，默认为当前模块所在目录
    """
    if prompts_dir is None:
      self.prompts_dir = Path(__file__).parent
    else:
      self.prompts_dir = Path(prompts_dir)

  def load(self, filename: str) -> str:
    """
    加载指定的提示词文件

    Args:
      filename: 文件名（包含扩展名）

    Returns:
      文件内容字符串

    Raises:
      FileNotFoundError: 文件不存在时抛出
    """
    file_path = self.prompts_dir / filename
    if not file_path.exists():
      raise FileNotFoundError(f"提示词文件不存在: {file_path}")
    return file_path.read_text(encoding="utf-8")

  def get_base_instruction(self) -> str:
    """
    获取基础指令

    Returns:
      基础指令内容
    """
    return self.load("base_instruction.txt")

  def get_persona(self, name: str) -> str:
    """
    获取指定人设的提示词

    Args:
      name: 人设名称 (mio/sage/kuro)

    Returns:
      人设提示词内容

    Raises:
      ValueError: 人设名称无效时抛出
    """
    name = name.lower()
    if name not in self.PERSONAS:
      raise ValueError(f"无效的人设名称: {name}，支持的人设: {self.PERSONAS}")
    return self.load(f"persona_{name}.txt")

  def get_full_system_prompt(self, persona: str) -> str:
    """
    获取完整的系统提示词（基础指令 + 人设）

    Args:
      persona: 人设名称 (mio/sage/kuro)

    Returns:
      完整的系统提示词
    """
    base = self.get_base_instruction()
    persona_prompt = self.get_persona(persona)
    return f"{base}\n\n{persona_prompt}"

  def list_personas(self) -> list[str]:
    """
    列出所有可用的人设

    Returns:
      人设名称列表
    """
    return self.PERSONAS.copy()
