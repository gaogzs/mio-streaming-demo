# memory 模块计划

## 模块职责

独立顶层分层记忆系统，基于 RAG 提供长期记忆能力。桥接 langchain_wrapper 和 streaming_studio 之间的记忆读写需求，避免两者之间的循环依赖。

## 设计理念

基于 spec/LOCAL_MEMORY.md 规范实现的四层记忆架构：
- **active**: 最近对话的短期记忆（FIFO），全量注入 prompt
- **temporary**: 从 active 溢出的记忆，通过 RAG 检索 + significance 衰减遗忘
- **summary**: 定期汇总浅层记忆的中长期记忆，通过 significance 衰减 + 定期清理
- **static**: 预设记忆（从 personas/{角色}/static_memories/ 加载），永不遗忘

## 文件结构

```
memory/
├── __init__.py         # 模块导出
├── config.py           # 全局配置（所有可调常量汇总）
├── significance.py     # significance 评分函数（独立，方便修改）
├── store.py            # VectorStore（Chroma 封装）
├── archive.py          # MemoryArchive（归档到 JSON）
├── formatter.py        # 记忆格式化（相对时间显示）
├── retriever.py        # MemoryRetriever 跨层检索 + LCEL Runnable
└── layers/
    ├── __init__.py     # 层级导出
    ├── base.py         # MemoryEntry 数据类
    ├── active.py       # ActiveLayer（FIFO + 溢出回调）
    ├── temporary.py    # TemporaryLayer（RAG + significance）
    ├── summary.py      # SummaryLayer（定期汇总 + 清理）
    └── static.py       # StaticLayer（预设记忆）
```

## 核心组件

### MemoryConfig (config.py)

所有可调常量汇总在一个文件中：

| 配置类 | 关键参数 |
|--------|----------|
| ActiveConfig | capacity=10 |
| TemporaryConfig | significance_threshold=0.1, decay_coefficient=0.95 |
| SummaryConfig | interval=300s, cleanup_ratio=0.01, decay_coefficient=0.98 |
| RetrievalConfig | mode="quota"/"weighted", 各层取回数量/权重 |
| EmbeddingConfig | model="BAAI/bge-small-zh-v1.5", persist_dir="data/memory_store" |

### Significance 评分 (significance.py)

独立函数，方便未来替换评分策略：

```python
initial_significance() -> 0.500
decay_significance(current, coefficient) -> current * coefficient
boost_significance(current) -> current + (1.0 - current) / 2.0
```

### VectorStore (store.py)

Chroma 向量存储封装，所有 RAG 层共享嵌入模型实例。

| 方法 | 说明 |
|------|------|
| `add(doc_id, content, metadata)` | 添加文档 |
| `search(query, top_k)` | 语义检索 |
| `delete(ids)` | 删除文档 |
| `update_metadata(doc_id, metadata)` | 更新元数据 |
| `get_all()` | 获取所有文档 |
| `count()` / `clear()` | 计数 / 清空 |

### MemoryRetriever (retriever.py)

跨层检索器，支持两种模式：

- **quota**: 每层分配固定取回数量
- **weighted**: 所有层合并取回，按层级系数加权重排

提供 `as_runnable() -> RunnableLambda` 用于 LCEL 集成。

### 格式化 (formatter.py)

- `format_active_memories()` — active 层格式化（时序列表）
- `format_retrieved_memories()` — RAG 层格式化（按层排序 + 相对时间）

## 使用示例

```python
from memory import (
  MemoryConfig, VectorStore, MemoryArchive,
  ActiveLayer, TemporaryLayer, SummaryLayer, StaticLayer,
  MemoryRetriever,
)

config = MemoryConfig()

# 创建共享嵌入模型和存储
store_temp = VectorStore("temporary", config.embedding)
store_sum = VectorStore("summary", config.embedding)
store_static = VectorStore("static", config.embedding)

archive = MemoryArchive("karin")

# 创建各层
active = ActiveLayer(config=config.active, on_overflow=temporary.add)
temporary = TemporaryLayer(store_temp, archive, config.temporary)
summary = SummaryLayer(store_sum, archive, config.summary)
static = StaticLayer(store_static, persona="karin")

# 跨层检索
retriever = MemoryRetriever(active, temporary, summary, static)
active_text, rag_text = retriever.retrieve("用户喜欢什么")

# LCEL 集成（未来使用）
runnable = retriever.as_runnable()
```

## 依赖方向

```
memory/retriever → memory/layers/* → memory/store, memory/archive
memory/layers/static → personas/{角色}/static_memories/
memory/store → chromadb, sentence-transformers
```

## 状态

- [x] 四层记忆实现 (active/temporary/summary/static)
- [x] VectorStore (Chroma 封装)
- [x] MemoryArchive (JSON 归档)
- [x] Significance 评分函数
- [x] 跨层检索器 (quota/weighted 模式)
- [x] LCEL Runnable 集成
- [x] 格式化工具
- [ ] 集成到 StreamingPipeline（待实现）
- [ ] Summary 层定时汇总触发（待实现）
