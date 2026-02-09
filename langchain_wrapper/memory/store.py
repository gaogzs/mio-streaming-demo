"""
RAG 记忆存储
使用 Chroma 向量数据库 + HuggingFace 嵌入模型实现记忆的存储与检索
"""

import logging
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from langchain_core.documents import Document
from langchain_chroma import Chroma
from langchain_huggingface import HuggingFaceEmbeddings

from .category import MemoryCategory

logger = logging.getLogger(__name__)


# 默认嵌入模型：中文优化的小型模型
_DEFAULT_MODEL = "BAAI/bge-small-zh-v1.5"

# 默认持久化目录
_DEFAULT_PERSIST_DIR = "data/memory_store"


@dataclass(frozen=True)
class MemoryMetadata:
  """记忆元数据（不可变）"""

  category: str
  timestamp: str
  source: Optional[str] = None
  user_id: Optional[str] = None

  def to_dict(self) -> dict:
    """转换为字典（过滤 None 值）"""
    result = {
      "category": self.category,
      "timestamp": self.timestamp,
    }
    if self.source is not None:
      result["source"] = self.source
    if self.user_id is not None:
      result["user_id"] = self.user_id
    return result


class MemoryStore:
  """
  RAG 记忆存储

  基于 Chroma 向量数据库，提供记忆的增删查功能。
  使用 HuggingFace 中文嵌入模型进行语义检索。
  """

  def __init__(
    self,
    persist_directory: str = _DEFAULT_PERSIST_DIR,
    embedding_model: str = _DEFAULT_MODEL,
    collection_name: str = "memories",
  ):
    """
    初始化记忆存储

    Args:
      persist_directory: Chroma 持久化目录
      embedding_model: HuggingFace 嵌入模型名称
      collection_name: Chroma collection 名称
    """
    self._embeddings = HuggingFaceEmbeddings(
      model_name=embedding_model,
    )
    self._vectorstore = Chroma(
      collection_name=collection_name,
      embedding_function=self._embeddings,
      persist_directory=persist_directory,
    )

  def add_memory(
    self,
    content: str,
    category: MemoryCategory,
    source: Optional[str] = None,
    user_id: Optional[str] = None,
  ) -> str:
    """
    添加单条记忆

    Args:
      content: 记忆内容文本
      category: 记忆类别
      source: 来源标识（可选）
      user_id: 用户ID（可选）

    Returns:
      记忆ID

    Raises:
      ValueError: content 为空
    """
    if not content or not content.strip():
      raise ValueError("content 不能为空")

    memory_id = str(uuid.uuid4())
    metadata = MemoryMetadata(
      category=category.value,
      timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
      source=source,
      user_id=user_id,
    )

    self._vectorstore.add_documents(
      documents=[Document(page_content=content, metadata=metadata.to_dict())],
      ids=[memory_id],
    )
    return memory_id

  def add_memories(
    self,
    contents: list[str],
    categories: list[MemoryCategory],
    source: Optional[str] = None,
    user_id: Optional[str] = None,
  ) -> list[str]:
    """
    批量添加记忆

    Args:
      contents: 记忆内容列表
      categories: 对应的类别列表（长度须与 contents 一致）
      source: 来源标识（可选，应用于所有记忆）
      user_id: 用户ID（可选，应用于所有记忆）

    Returns:
      记忆ID列表

    Raises:
      ValueError: contents 和 categories 长度不一致
    """
    if len(contents) != len(categories):
      raise ValueError(
        f"contents 长度 ({len(contents)}) 与 categories 长度 ({len(categories)}) 不一致"
      )
    for i, content in enumerate(contents):
      if not content or not content.strip():
        raise ValueError(f"contents[{i}] 不能为空")

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    ids = [str(uuid.uuid4()) for _ in contents]
    documents = []

    for content, category in zip(contents, categories):
      metadata = MemoryMetadata(
        category=category.value,
        timestamp=now,
        source=source,
        user_id=user_id,
      )
      documents.append(
        Document(page_content=content, metadata=metadata.to_dict())
      )

    self._vectorstore.add_documents(documents=documents, ids=ids)
    return ids

  def retrieve(
    self,
    query: str,
    top_k: int = 5,
    category_filter: Optional[MemoryCategory] = None,
  ) -> list[tuple[Document, float]]:
    """
    检索相关记忆

    Args:
      query: 查询文本
      top_k: 返回的最大结果数
      category_filter: 按类别过滤（可选）

    Returns:
      (Document, 相似度分数) 元组列表，按相关性降序排列
    """
    search_kwargs: dict = {"k": top_k}
    if category_filter is not None:
      search_kwargs["filter"] = {"category": category_filter.value}

    return self._vectorstore.similarity_search_with_score(
      query=query,
      **search_kwargs,
    )

  def delete(self, memory_id: str) -> bool:
    """
    删除指定记忆

    Args:
      memory_id: 记忆ID

    Returns:
      是否成功删除
    """
    try:
      self._vectorstore.delete(ids=[memory_id])
      return True
    except Exception as e:
      logger.error("删除记忆失败 (id=%s): %s", memory_id, e)
      return False

  def clear(self) -> None:
    """清空所有记忆"""
    # langchain-chroma 未提供 clear 公共 API，需访问底层 collection
    collection = self._vectorstore._collection
    all_data = collection.get()
    if all_data["ids"]:
      collection.delete(ids=all_data["ids"])

  def count(self) -> int:
    """获取记忆总数"""
    # langchain-chroma 未提供 count 公共 API，需访问底层 collection
    return self._vectorstore._collection.count()
