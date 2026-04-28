"""
初始化黑话与标签数据生成脚本
调用大模型生成一批初始的标签和黑话，保存为 JSON 文件，用于后续导入
"""

import asyncio
import json
import sys
from pathlib import Path

# 将项目根目录添加到路径
project_root = Path(__file__).parent.parent
if str(project_root) not in sys.path:
  sys.path.insert(0, str(project_root))

from langchain_wrapper.model_provider import ModelProvider


async def generate_tags(model) -> str:
  prompt = """
  你是虚拟直播间设计专家。请生成 5 个虚拟直播间常见的观众群体或人设标签。
  输出必须是纯 JSON 数组格式，不要包含 Markdown 代码块标记（如 ```json）。

  输出 JSON Schema:
  [
    {
      "name": "标签名（如：纯良粉丝、乐子人、技术宅、二次元等）",
      "definition": "该群体的简要定义与行为特征",
      "examples": ["典型弹幕例句1", "典型弹幕例句2"],
      "related_tags": ["相关标签1", "相关标签2"],
      "confidence": 0.95
    }
  ]
  """
  res = await model.ainvoke(prompt)
  return res.content if hasattr(res, "content") else str(res)


async def generate_jargons(model, tag_names: list[str]) -> str:
  prompt = f"""
  基于以下标签/群体，请生成 10 个虚拟直播间或网络上常见的黑话（网络流行语或直播梗）。
  可用标签：{tag_names}
  
  输出必须是纯 JSON 数组格式，不要包含 Markdown 代码块标记。

  输出 JSON Schema:
  [
    {{
      "entry_id": "init_jargon_001",
      "phrase": "（词汇本身，如：破防、急了、上头、下饭等）",
      "brief": "（一句话简要含义）",
      "details": "（详细用法、来源、与情感关联）",
      "tags": ["（包含在上述标签中的1到2个适合该黑话的人群标签）"],
      "status": "known",
      "confidence": 0.9,
      "source_refs": ["init_generation"]
    }}
  ]
  """
  res = await model.ainvoke(prompt)
  return res.content if hasattr(res, "content") else str(res)


def clean_json(text: str) -> str:
  text = text.strip()
  if text.startswith("```"):
    text = text.split("\n", 1)[-1]
  if text.endswith("```"):
    text = text.rsplit("```", 1)[0]
  return text.strip()


async def main():
  print("正在初始化大模型...")
  # 这里使用大模型或者小模型皆可
  model = ModelProvider.remote_small() 
  
  print("\n=== 开始生成标签数据 ===")
  tags_raw = await generate_tags(model)
  tags_json_str = clean_json(tags_raw)
  
  try:
    tags_data = json.loads(tags_json_str)
    print(f"成功生成 {len(tags_data)} 个标签。")
  except Exception as e:
    print(f"解析标签 JSON 失败: {e}\n模型原始内容:\n{tags_raw}")
    return

  tag_names = [t.get("name") for t in tags_data if t.get("name")]
  
  print("\n=== 开始生成黑话数据 ===")
  jargons_raw = await generate_jargons(model, tag_names)
  jargons_json_str = clean_json(jargons_raw)
  
  try:
    jargons_data = json.loads(jargons_json_str)
    print(f"成功生成 {len(jargons_data)} 个黑话。")
  except Exception as e:
    print(f"解析黑话 JSON 失败: {e}\n模型原始内容:\n{jargons_raw}")
    return

  # 保存到文件
  out_dir = project_root / "data" / "init_jargon_data"
  out_dir.mkdir(parents=True, exist_ok=True)
  
  tags_file = out_dir / "init_tags.json"
  tags_file.write_text(json.dumps(tags_data, ensure_ascii=False, indent=2), encoding="utf-8")
  print(f"\n标签已保存至: {tags_file}")
  
  jargons_file = out_dir / "init_jargons.json"
  jargons_file.write_text(json.dumps(jargons_data, ensure_ascii=False, indent=2), encoding="utf-8")
  print(f"黑话已保存至: {jargons_file}")

  print("\n你可以使用以下方式在代码中导入:")
  print(f"manager.import_tags_from_json('{tags_file.as_posix()}')")
  print(f"manager.import_known_jargons_from_json('{jargons_file.as_posix()}')")


if __name__ == "__main__":
  asyncio.run(main())
