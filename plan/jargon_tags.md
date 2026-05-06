# jargon_tags 模块计划

## 模块目标

为虚拟主播新增“黑话 + 标签”双系统：

1. 让主播能在互动中学习新黑话，并持续修订已有条目。
2. 通过标签约束黑话使用范围，避免风格漂移和出戏。
3. 以异步为主接入主流程，尽量不增加单次回复延迟。
4. 支持人工导入、AI 自动学习、调试台可观测。

## 设计原则

1. 与现有 memory/topic_manager 风格一致：独立顶层模块 + manager 编排 + debug_state。
2. 数据层同时支持逐字匹配和向量检索。
3. 模型调用分层：同步路径只做轻量检索；重判断放后台任务。
4. 所有可调参数集中到 config，避免硬编码。

## 新增目录结构

```
jargon_tags/
  __init__.py
  config.py                # 全局配置
  models.py                # 数据类（黑话、待解明条目、标签、主播标签状态）
  store.py                 # 黑话/标签存储封装（向量+元数据）
  archive.py               # JSON 导入导出与人工录入接口
  retriever.py             # 逐字匹配 + 向量召回 + 标签过滤
  judge.py                 # 黑话判官（新词发现/解释识别/条目修订）
  tag_judge.py             # 标签判官（标签演化+主播标签轮换建议）
  formatter.py             # prompt 片段格式化
  manager.py               # 顶层编排器（推荐入口）
```

建议新增 prompt 模板：

```
prompts/jargon/
  discover_and_resolve.txt     # 黑话判官主提示词
  revise_known_entry.txt       # 已知黑话修订提示词（可选）
  tag_evolution.txt            # 标签判官提示词
  ask_pending_jargon.txt       # 提问待解明黑话的提示片段
  reference_mode_hint.txt      # 参考模式注入提示
  polish_mode_rewrite.txt      # 润色模式重写提示
```

## 数据模型设计

### 1) 已知黑话条目 JargonEntry

字段建议：

- phrase: 黑话原文
- brief: 简要含义（检索展示）
- details: 详细信息对象
- tags: 标签列表
- status: known 或 unresolved_resolved
- confidence: 0~1
- source_refs: 来源数组（可追溯）
- created_at / updated_at
- version

details 子结构：

- origin: 来源说明
- meaning: 详细含义
- distinctions: 与近义黑话差异
- usage: 用法
- examples:
  - plain: 正常表达
  - jargon: 黑话表达

### 2) 待解明条目 PendingJargon

- phrase
- first_seen_at
- last_seen_at
- seen_count
- asked_count
- last_asked_at
- candidate_brief
- candidate_tags
- notes
- status: pending 或 abandoned

### 3) 标签条目 TagEntry

- name
- definition
- examples
- related_tags
- created_at / updated_at
- confidence

### 4) 主播当前标签状态 StreamerTagState

- active_tags: 当前生效标签
- candidate_tags: 候选标签
- last_rotate_at
- rotation_cursor

## 存储与检索设计

### 黑话存储

1. 向量库：沿用 Chroma 封装思路，文档内容由 phrase + brief + meaning + usage 拼接。
2. 精确匹配索引：内存字典 phrase -> entry_id，支持逐字命中。
3. JSON 归档：支持人工导入导出，便于维护和热修。

### 待解明存储

1. 单独集合，不混入已知黑话。
2. 支持按 asked_count、last_seen_at、seen_count 排序抓取。

### 标签存储

1. 标签本体使用独立集合。
2. 黑话条目与标签通过 tags 字段关联。

### 检索流程 Retriever

对任意输入文本执行：

1. 逐字命中 phrase。
2. 关键词切分后做短文本向量检索。
3. 合并去重并计算得分。
4. 叠加主播 active_tags 过滤和加权。
5. 输出用于 prompt 的候选黑话片段。

## 判官流程设计

## 关键问题：一个 LLM 请求还是多个请求

推荐“1 主请求 + 可选修订请求”的混合方案：

1. 主请求 discover_and_resolve：
   - 输入：最近评论窗口 + 相关已知黑话 + 待解明条目。
   - 输出：
     - 新疑似黑话
     - 对待解明黑话的解释判定
     - 对已知黑话是否建议修订
2. 可选修订请求 revise_known_entry：
   - 仅当主请求标记 high_confidence_revision 时触发。
   - 作用：生成结构化修订内容并做字段级更新。

理由：

1. 单请求可减少调用数，保证吞吐。
2. 修订是高风险动作，拆成可选二次请求更稳。
3. 与“异步后台处理”目标一致。

## 黑话学习状态机

每轮后台分析后，对每个条目执行：

1. 新疑似黑话：加入 pending。
2. 待解明收到充分解释：
   - pending 删除
   - 转 known 并入库
3. 待解明收到部分解释：
   - pending 更新 notes
   - 同时生成低置信 known 条目（可后续修订）
4. 判定为自然表达：
   - 仍转 known（标注 normal_expression）
5. 无解释：
   - asked_count 超阈值前继续追问
   - 达阈值后标记 abandoned，并写入 known（no_explanation）避免重复追问

## 与主 prompt 的交互

支持两种模式（config 可切换）：

### A. 参考模式 reference

1. 在主回复前检索相关黑话。
2. 以“可选参考”片段注入 prompt，不强制改写。
3. 额外注入“待解明提问建议”列表（数量受限）。

优点：延迟低，流程简单。

### B. 润色模式 polish

1. 先得到原始回复。
2. 对原始回复分句检索可替换黑话。
3. 触发二次改写请求，仅做语言风格润色，不改变事实语义。

优点：黑话融合更自然。
缺点：增加一次调用和时延。

默认建议：reference，调试稳定后再启用 polish。

## 标签系统设计

### 标签判官职责

周期性读取评论窗口并输出：

1. 是否需要新增或修订 TagEntry。
2. 是否建议替换主播 active_tags 中的一部分。
3. 是否建议触发“间接提问群体定义”。

### 主播标签轮换

1. 低频轮换（例如每 N 分钟或 N 轮回复）。
2. 每次仅替换 1 个标签，保持人格连续性。
3. 新标签先进入 candidate，达到阈值后升为 active。

### 标签对黑话检索的作用

1. 强过滤：完全不相容标签可直接排除。
2. 软加权：相容标签提升召回得分。
3. 回退策略：过滤后为空时允许少量“普通网民”黑话兜底。

## 与 streaming_studio 的接入点

在 studio 中仿照 topic_manager 接入：

1. 新增开关与实例：enable_jargon_tags。
2. 在 send_comment 时转发 comment 给 jargon manager（非阻塞）。
3. 在生成 prompt 前调用 format_context 注入黑话参考与待提问项。
4. 在回复后调用 post_reply（异步），触发学习与修订。
5. 提供 jargon_debug_state 供调试台读取。

## 与 debug_console 的接入

扩展 state collector 和 monitor 页面：

1. state_collector 增加 jargon_tags 快照。
2. monitor 新增“黑话与标签”卡片，显示：
   - 已知黑话数量
   - 待解明数量
   - 本轮新学条目
   - active_tags
   - 最近判官决策
   - 是否处于 reference 或 polish

## 配置建议

在 config.py 集中定义：

- mode: reference 或 polish
- analysis_interval_seconds
- comment_window_size
- pending_question_max_per_reply
- pending_question_pick_mode: model_decide 或 random_k
- pending_abandon_threshold
- tag_rotation_interval_seconds
- active_tag_count
- retrieval_top_k
- exact_match_boost
- vector_match_boost
- tag_match_boost
- revision_confidence_threshold

## 实施分期

## 当前进度（2026-04-27）

- [x] Phase 1 基础闭环：数据模型、存储、reference 注入、pending 迁移、debug_state
- [x] studio 接入：enable_jargon_tags 开关、生命周期、回复后异步学习
- [x] debug_console 接入：状态采集与监控卡片
- [x] LLM 判官初版：discover_and_resolve + tag_evolution 的 JSON 结构化处理
- [x] polish 模式二次改写（与流式冲突时自动降级为非流式）
- [x] 标签低频轮换策略（按时间窗口渐进替换，每次最多替换 1 个）
- [x] 启动参数支持模式切换（reference/polish）
- [x] 接入基于时间和主循环的按天重要度（weight）平滑衰减。
- [x] 使用联网 Agent（DuckDuckGo 工具搜索）增强初始预设黑话数据集的内容质量。

### Phase 1: 最小可用闭环

1. 数据模型 + 存储 + 人工导入接口
2. reference 模式注入
3. 黑话判官主请求
4. pending 状态机
5. debug_state 基础字段

### Phase 2: 标签系统

1. 标签库与标签判官
2. active_tags 轮换
3. 检索标签过滤与加权

### Phase 3: 润色模式

1. 原回复分句检索
2. 二次改写调用
3. 语义一致性保护

### Phase 4: 调试增强与稳定性

1. monitor 面板扩展
2. 异常恢复与降级路径
3. 参数调优

## 自我审查清单

1. 是否保持主链路异步，避免阻塞直播回复。
2. 是否提供了人工导入和 AI 自动学习双入口。
3. 是否实现 pending 到 known 的完整状态迁移。
4. 是否避免重复追问并支持放弃机制。
5. 是否有标签约束，避免黑话风格失控。
6. 是否支持 reference 和 polish 模式切换。
7. 是否已定义 debug_state 并接入调试台。

## 编码起步清单（下一步）

1. [x] 新建 jargon_tags 目录与基础文件：__init__, config, models, manager。
2. [x] 新建 prompts/jargon 模板文件骨架。
3. [x] 在 streaming_studio 添加 enable_jargon_tags 开关与生命周期接入。
4. [x] 在 debug_console 增加 jargon_tags 状态展示。
5. [x] 增加基础测试脚本（pending 迁移、标签轮换、polish 回退）。
6. [x] 补齐 JSON 手动导入接口（黑话/标签）。
