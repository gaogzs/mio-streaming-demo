"""
初始化黑话与标签数据生成脚本
调用大模型或Agent生成一批初始的标签和黑话，保存为 JSON 文件，用于后续导入
"""

import argparse
import asyncio
import json
import sys
from pathlib import Path

# 将项目根目录添加到路径
project_root = Path(__file__).parent.parent
if str(project_root) not in sys.path:
  sys.path.insert(0, str(project_root))

from langchain_wrapper.model_provider import ModelProvider
try:
  from langchain_wrapper.agent import create_search_agent
except ImportError:
  create_search_agent = lambda x, **kwargs: x


def clean_json(text: str) -> str:
  text = text.strip()
  if text.startswith("```"):
    text = text.split("\n", 1)[-1]
  if text.endswith("```"):
    text = text.rsplit("```", 1)[0]
  return text.strip()


async def generate_tags(model_or_agent, existing_tags: list[str]) -> str:
  prompt = f"""
  你是虚拟直播间设计专家。请生成 5 个虚拟直播间常见的观众群体或人设标签。
  输出必须是纯 JSON 数组格式，不要包含 Markdown 代码块标记（如 ```json）。

  【已有标签，不要重复以下标签】：
  {", ".join(existing_tags) if existing_tags else "无"}

  输出 JSON Schema:
  [
    {{
      "name": "标签名（如：纯良粉丝、乐子人、技术宅、二次元等）",
      "definition": "该群体的简要定义与行为特征",
      "examples": ["典型弹幕例句1", "典型弹幕例句2"],
      "related_tags": ["相关标签1", "相关标签2"],
      "confidence": 0.95
    }}
  ]
  """
  
  if hasattr(model_or_agent, "ainvoke"):
    res = await model_or_agent.ainvoke(prompt)
    if isinstance(res, dict) and "output" in res:
      return res["output"]
    return res.content if hasattr(res, "content") else str(res)
  elif hasattr(model_or_agent, "arun"):
    return await model_or_agent.arun(prompt)
  else:
    raise ValueError("不支持的模型或代理类型")


async def generate_jargons(model_or_agent, tag_names: list[str], existing_jargons: list[str]) -> str:
  prompt = f"""
  基于以下标签/群体，请生成 10 个近期虚拟直播间或网络上常见的黑话（网络流行语或直播梗）。
  如果带有搜索工具，请先自行搜索“近期网络直播流行语 黑话 梗”以获取最新信息。
  
  可用人群标签：{tag_names}
  
  【已有黑话，不要重复生成以下词语】：
  {", ".join(existing_jargons) if existing_jargons else "无"}

  请不要输出多余格式，直接输出纯 JSON 数组，包含具体字段：

  输出 JSON Schema:
  [
    {{
      "entry_id": "init_jargon_001",
      "phrase": "（词汇本身，如：破防、急了、上头、下饭等）",
      "brief": "（一句话简要含义）",
      "details": "（详细用法、来源、与情感关联）",
      "tags": ["（包含在上述标签中的1到2个适合该黑话的人群标签）"],
      "examples": ["正常表达: ...", "黑话表达: ..."],
      "status": "known",
      "confidence": 0.9,
      "source_refs": ["init_generation"]
    }}
  ]
  """
  
  if hasattr(model_or_agent, "ainvoke"):
    res = await model_or_agent.ainvoke(prompt)
    if isinstance(res, dict) and "output" in res:
      return res["output"]
    return res.content if hasattr(res, "content") else str(res)
  elif hasattr(model_or_agent, "arun"):
    return await model_or_agent.arun(prompt)
  else:
    raise ValueError("不支持的模型或代理类型")


async def main():
  parser = argparse.ArgumentParser()
  parser.add_argument("--use-agent", action="store_true", help="使用带有联网搜索能力的 Agent")
  args = parser.parse_args()

  print("正在初始化大模型...")
  base_model = ModelProvider.remote_large() 
  model = create_search_agent(base_model) if args.use_agent else base_model
  
  out_dir = project_root / "data" / "init_jargon_data"
  out_dir.mkdir(parents=True, exist_ok=True)
  
  tags_file = out_dir / "init_tags.json"
  jargons_file = out_dir / "init_jargons.json"

  existing_tags = []
  existing_jargons = []
  
  if tags_file.exists():
    try:
      existing_tags = [t["name"] for t in json.loads(tags_file.read_text("utf-8")) if "name" in t]
    except Exception:
      pass

  if jargons_file.exists():
    try:
      existing_jargons = [j["phrase"] for j in json.loads(jargons_file.read_text("utf-8")) if "phrase" in j]
    except Exception:
      pass

  print(f"\n=== 开始生成标签数据 (已有 {len(existing_tags)} 个标签) ===")
  tags_raw = await generate_tags(model, existing_tags)
  tags_json_str = clean_json(tags_raw)
  
  tags_data = []
  try:
    tags_data = json.loads(tags_json_str)
    print(f"解析成功，生成 {len(tags_data)} 个标签。")
  except Exception as e:
    print(f"解析标签 JSON 失败: {e}\n模型原始内容:\n{tags_raw}")
    return

  combined_tags = existing_tags + [t.get("name") for t in tags_data if t.get("name")]
  tag_names = list(set(combined_tags))

  print(f"\n=== 开始生成黑话数据 (已有 {len(existing_jargons)} 个黑话) ===")
  jargons_raw = await generate_jargons(model, tag_names, existing_jargons)
  jargons_json_str = clean_json(jargons_raw)
  
  jargons_data = []
  try:
    jargons_data = json.loads(jargons_json_str)
    print(f"解析成功，生成 {len(jargons_data)} 个黑话。")
  except Exception as e:
    print(f"解析黑话 JSON 失败: {e}\n模型原始内容:\n{jargons_raw}")
    return
  
  # 如果已有文件，先读取追加，避免覆写
  if tags_file.exists():
    old_tags = json.loads(tags_file.read_text("utf-8"))
    tags_data = old_tags + list(tags_data)

  if jargons_file.exists():
    old_jargons = json.loads(jargons_file.read_text("utf-8"))
    jargons_data = old_jargons + list(jargons_data)

  tags_file.write_text(json.dumps(tags_data, ensure_ascii=False, indent=2), encoding="utf-8")
  print(f"\n标签已存至: {tags_file}")
  
  jargons_file.write_text(json.dumps(jargons_data, ensure_ascii=False, indent=2), encoding="utf-8")
  print(f"黑话已存至: {jargons_file}")

  print("\n生成完毕！现在可以使用 scripts/import_init_data.py 将数据导入到本地库。")


if __name__ == "__main__":
  asyncio.run(main())
