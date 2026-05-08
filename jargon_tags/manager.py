"""
黑话与标签系统编排器
"""

import asyncio
import logging
import uuid
from datetime import datetime
from typing import Optional, TYPE_CHECKING

from langchain_core.language_models import BaseChatModel
from langchain_wrapper.model_provider import ModelType

from prompts import PromptLoader

from .archive import (
  export_known_jargons,
  export_tags,
  import_known_jargons,
  import_tags,
)
from .config import JargonTagsConfig
from .formatter import format_reference_context, pick_pending_questions
from .judge import (
  extract_candidate_phrases,
  normalize_discover_output,
  parse_json_response,
)
from .models import (
  JargonEntry,
  PendingJargon,
  TagEntry,
  StreamerTagState,
  JargonDecision,
)
from .retriever import JargonRetriever
from .store import JargonStore
from .tag_judge import normalize_tag_output

if TYPE_CHECKING:
  from streaming_studio.database import CommentDatabase
  from streaming_studio.models import Comment

logger = logging.getLogger(__name__)


class JargonTagsManager:
  """
  黑话与标签系统顶层编排器

  Phase 1 能力：
  - 评论中疑似黑话候选发现（规则版判官）
  - 待解明条目管理与追问次数控制
  - 已知黑话逐字 + 向量检索
  - 参考模式 prompt 注入
  """

  def __init__(
    self,
    persona: str,
    database: "CommentDatabase",
    config: JargonTagsConfig | None = None,
    judge_model: Optional[BaseChatModel] = None,
    model_type: ModelType = ModelType.OPENAI,
  ):
    self._persona = persona
    self._database = database
    self._config = config or JargonTagsConfig()
    self._judge_model = judge_model
    self._model_type = model_type
    self._prompt_loader = PromptLoader()

    self._store = JargonStore()
    self._retriever = JargonRetriever(
      store=self._store,
      exact_match_boost=self._config.exact_match_boost,
      vector_match_boost=self._config.vector_match_boost,
      tag_match_boost=self._config.tag_match_boost,
      indirect_tag_match_boost=self._config.indirect_tag_match_boost,
    )

    self._tag_state = StreamerTagState(active_tags=("普通网民",))
    self._current_questions: tuple[str, ...] = tuple()
    self._indirect_question_hints: tuple[str, ...] = tuple()
    self._last_retrieved_jargons: tuple[str, ...] = tuple()

    self._decision_log: list[JargonDecision] = []
    self._pending_comments: list["Comment"] = []

    self._analysis_task: asyncio.Task | None = None
    self._running = False

  @property
  def is_polish_mode(self) -> bool:
    """是否处于润色模式"""
    return self._config.mode == "polish"

  async def start(self) -> None:
    """启动后台分析循环"""
    if self._running:
      return
    self._running = True
    self._analysis_task = asyncio.create_task(self._analysis_loop())

  async def stop(self) -> None:
    """停止后台分析循环"""
    self._running = False
    if self._analysis_task is not None:
      self._analysis_task.cancel()
      try:
        await self._analysis_task
      except asyncio.CancelledError:
        pass
      self._analysis_task = None

  def on_comment(self, comment: "Comment") -> None:
    """接收新弹幕（非阻塞）"""
    if not self._running:
      return
    self._pending_comments.append(comment)

  def format_context(self, comments: list["Comment"]) -> str:
    """
    生成注入主 prompt 的黑话上下文（参考模式）

    当前骨架只返回占位文本。
    """
    if self._config.mode != "reference":
      return ""

    if not comments:
      return ""

    texts = [c.content for c in comments if c.content.strip()]
    entries = self._retriever.retrieve_for_texts(
      texts=texts,
      active_tags=self._tag_state.active_tags,
      top_k=self._config.retrieval_top_k,
    )
    
    self._last_retrieved_jargons = tuple(e.phrase for e in entries)

    pending_items = self._store.list_pending()
    pending_items = [
      item for item in pending_items
      if item.status == "pending"
      and item.asked_count < self._config.pending_abandon_threshold
    ]
    to_ask = pick_pending_questions(
      pending_items=pending_items,
      max_count=self._config.pending_question_max_per_reply,
      pick_mode=self._config.pending_question_pick_mode,
    )

    for item in to_ask:
      self._store.mark_pending_asked(item.phrase)
    self._current_questions = tuple(item.phrase for item in to_ask)

    # 查出完整的 TagEntry 以支持例句注入
    active_tag_entries = []
    for tag_name in self._tag_state.active_tags:
      tag = self._store.find_tag_by_name(tag_name)
      if tag:
        active_tag_entries.append(tag)

    return format_reference_context(
      entries=entries,
      active_tags=tuple(active_tag_entries),
      pending_to_ask=to_ask,
      indirect_hints=self._indirect_question_hints,
    )

  async def post_reply(
    self,
    prompt: str,
    response: str,
    comments: list["Comment"],
  ) -> None:
    """
    回复后处理

    当前阶段采用规则判定：
    - 从评论中提取疑似黑话候选
    - 维护 pending 集合
    - 对超过追问阈值的条目执行放弃并转入已知
    """
    _ = prompt
    _ = response
    self._learn_from_comments(comments)
    self._promote_abandoned_pending()
    
    # 执行时间权重衰减（计算时间差）
    self._store.decay_all_weights(
        self._config.weight_decay_coefficient,
        self._config.weight_archive_threshold
    )

  async def polish_response(
    self,
    original_response: str,
    comments: list["Comment"],
  ) -> str:
    """
    润色模式：基于原回复和候选黑话二次改写

    失败时回退原回复，保证主流程稳定。
    """
    if not self.is_polish_mode:
      return original_response

    original_response = original_response.strip()
    if not original_response:
      return original_response

    texts = [c.content for c in comments if c.content.strip()]
    texts.append(original_response)
    entries = self._retriever.retrieve_for_texts(
      texts=texts,
      active_tags=self._tag_state.active_tags,
      top_k=self._config.retrieval_top_k,
    )
    self._last_retrieved_jargons = tuple(e.phrase for e in entries)

    if not entries:
      return original_response

    try:
      model = self._get_model()
    except Exception as exc:
      logger.warning("初始化润色模型失败，回退原回复: %s", exc)
      return original_response

    candidate_text = "\n".join(
      f"- {e.phrase}: {e.brief}（标签: {'、'.join(e.tags) if e.tags else '普通网民'}）"
      for e in entries
    )

    prompt_tpl = self._prompt_loader.load("jargon/polish_mode_rewrite.txt")
    prompt = prompt_tpl.format(
      persona=self._persona,
      active_tags="、".join(self._tag_state.active_tags) or "普通网民",
      original_response=original_response,
      candidate_jargons=candidate_text,
    )

    try:
      result = await model.ainvoke(prompt)
      rewritten = result.content if hasattr(result, "content") else str(result)
      rewritten = rewritten.strip()
      if not rewritten:
        return original_response
      return rewritten
    except Exception as exc:
      logger.warning("润色请求失败，回退原回复: %s", exc)
      return original_response

  def upsert_jargon(self, entry: JargonEntry) -> None:
    """人工或自动写入黑话条目"""
    self._store.upsert_known(entry)

  def upsert_tag(self, entry: TagEntry) -> None:
    """人工或自动写入标签条目"""
    self._store.upsert_tag(entry)

  def import_known_jargons_from_json(self, path: str) -> int:
    """从 JSON 批量导入已知黑话，返回导入条数"""
    entries = import_known_jargons(path)
    for entry in entries:
      self._store.upsert_known(entry)
    return len(entries)

  def import_tags_from_json(self, path: str) -> int:
    """从 JSON 批量导入标签，返回导入条数"""
    entries = import_tags(path)
    for entry in entries:
      self._store.upsert_tag(entry)
    return len(entries)

  def export_known_jargons_to_json(self, path: str) -> None:
    """导出已知黑话到 JSON"""
    export_known_jargons(path, self._store.list_known())

  def export_tags_to_json(self, path: str) -> None:
    """导出标签到 JSON"""
    export_tags(path, self._store.list_tags())

  def debug_state(self) -> dict:
    """调试快照"""
    return {
      "running": self._running,
      "mode": self._config.mode,
      "known_jargon_count": len(self._store.list_known()),
      "pending_jargon_count": len(self._store.list_pending()),
      "tag_count": len(self._store.list_tags()),
      "active_tags": list(self._tag_state.active_tags),
      "current_questions": list(self._current_questions),
      "indirect_question_hints": list(self._indirect_question_hints),
      "last_retrieved_jargons": list(self._last_retrieved_jargons),
      "vector_enabled": self._store.vector_enabled,
      "pending_comments": len(self._pending_comments),
      "last_decision": (
        {
          "new_pending_count": self._decision_log[-1].new_pending_count,
          "new_pending_phrases": list(self._decision_log[-1].new_pending_phrases),
          "resolved_count": self._decision_log[-1].resolved_count,
          "resolved_phrases": list(self._decision_log[-1].resolved_phrases),
          "revised_count": self._decision_log[-1].revised_count,
          "notes": self._decision_log[-1].notes,
          "analyzed_at": self._decision_log[-1].analyzed_at.isoformat(),
        }
        if self._decision_log
        else None
      ),
      "analysis_task_running": (
        self._analysis_task is not None and not self._analysis_task.done()
      ),
    }

  async def _analysis_loop(self) -> None:
    """后台分析循环（异步，不阻塞主回复链路）"""
    interval = self._config.analysis_interval_seconds
    while self._running:
      try:
        await asyncio.sleep(interval)
        if not self._pending_comments:
          continue

        comments = list(self._pending_comments)
        self._pending_comments.clear()
        comments = comments[-self._config.comment_window_size :]

        self._learn_from_comments(comments)
        await self._run_llm_judges(comments)
        self._promote_abandoned_pending()

        # 仅为记录处理了多少条（具体新增由后续逻辑添加）
        # self._decision_log.append(
        #   JargonDecision(
        #     notes=f"分析循环完成，处理评论 {len(comments)} 条",
        #     analyzed_at=datetime.now(),
        #   )
        # )
      except asyncio.CancelledError:
        break
      except Exception as exc:
        logger.exception("黑话分析循环失败: %s", exc)

  def _get_model(self) -> BaseChatModel:
    """获取小模型（延迟初始化）"""
    if self._judge_model is None:
      from langchain_wrapper.model_provider import ModelProvider
      self._judge_model = ModelProvider.remote_small(self._model_type)
    return self._judge_model

  async def _run_llm_judges(self, comments: list["Comment"]) -> None:
    """执行 LLM 黑话判官与标签判官（可降级）"""
    if not self._config.enable_llm_judge:
      return

    if not comments:
      return

    try:
      model = self._get_model()
    except Exception as exc:
      logger.warning("初始化判官模型失败，跳过 LLM 判官: %s", exc)
      return

    await asyncio.gather(
      self._run_discover_and_resolve(model, comments),
      self._run_tag_evolution(model, comments),
      return_exceptions=True,
    )

  async def _run_discover_and_resolve(
    self,
    model: BaseChatModel,
    comments: list["Comment"],
  ) -> None:
    """运行黑话判官并应用结果"""
    comments_text = "\n".join(
      f"- {c.nickname}: {c.content}" for c in comments
    )

    related_entries = self._retriever.retrieve_for_texts(
      texts=[c.content for c in comments if c.content.strip()],
      active_tags=self._tag_state.active_tags,
      top_k=self._config.llm_related_known_limit,
    )
    related_text = "\n".join(
      f"- {e.phrase}: {e.brief}（标签: {'、'.join(e.tags) if e.tags else '普通网民'}）"
      for e in related_entries
    ) or "（无）"

    pending_items = self._store.list_pending()[: self._config.llm_pending_limit]
    pending_text = "\n".join(
      f"- {p.phrase} | 已追问 {p.asked_count} 次 | 备注: {p.notes or '无'}"
      for p in pending_items
    ) or "（无）"

    prompt_tpl = self._prompt_loader.load("jargon/discover_and_resolve.txt")
    prompt = prompt_tpl.format(
      comments=comments_text,
      related_known=related_text,
      pending_items=pending_text,
      active_tags="、".join(self._tag_state.active_tags) or "普通网民",
    )

    result = await model.ainvoke(prompt)
    text = result.content if hasattr(result, "content") else str(result)
    data = parse_json_response(text)
    if data is None:
      logger.warning("黑话判官返回无法解析 JSON")
      return

    normalized = normalize_discover_output(data)
    self._apply_discover_output(normalized)

  async def _run_tag_evolution(
    self,
    model: BaseChatModel,
    comments: list["Comment"],
  ) -> None:
    """运行标签判官并应用结果"""
    comments_text = "\n".join(
      f"- {c.nickname}: {c.content}" for c in comments
    )

    tags = self._store.list_tags()
    tags_text = "\n".join(
      f"- {t.name}: {t.definition}" for t in tags
    ) or "（无）"

    prompt_tpl = self._prompt_loader.load("jargon/tag_evolution.txt")
    prompt = prompt_tpl.format(
      comments=comments_text,
      tags=tags_text,
      active_tags="、".join(self._tag_state.active_tags) or "普通网民",
    )

    result = await model.ainvoke(prompt)
    text = result.content if hasattr(result, "content") else str(result)
    data = parse_json_response(text)
    if data is None:
      logger.warning("标签判官返回无法解析 JSON")
      return

    normalized = normalize_tag_output(data)
    self._apply_tag_output(normalized)

  def _apply_discover_output(self, data: dict) -> None:
    """应用黑话判官结果"""
    new_pending = 0
    resolved = 0
    revised = 0

    for item in data.get("new_candidates", []):
      phrase = str(item.get("phrase", "")).strip()
      if not phrase:
        continue
      if self._store.find_known_by_phrase(phrase) is not None:
        continue
      if self._store.find_pending_by_phrase(phrase) is not None:
        self._store.mark_pending_seen(phrase)
        continue

      tags = tuple(item.get("tags", [])) if isinstance(item.get("tags", []), list) else tuple()
      self._store.upsert_pending(
        PendingJargon(
          phrase=phrase,
          candidate_brief=str(item.get("brief", "待解明黑话候选"))[:60],
          candidate_tags=tags or self._tag_state.active_tags,
          notes="来自 LLM 判官候选",
        )
      )
      new_pending += 1

    for item in data.get("pending_resolutions", []):
      phrase = str(item.get("phrase", "")).strip()
      if not phrase:
        continue

      status = str(item.get("status", ""))
      brief = str(item.get("brief", "")).strip() or "来自互动解释"
      details = str(item.get("details", "")).strip() or "基于评论中的解释信息整理"
      tags = tuple(item.get("tags", [])) if isinstance(item.get("tags", []), list) else tuple()

      if status in {"resolved", "natural", "partial"}:
        self._store.upsert_known(
          JargonEntry(
            entry_id=f"jargon_{uuid.uuid4().hex[:12]}",
            phrase=phrase,
            brief=brief,
            details=details,
            tags=tags or self._tag_state.active_tags,
            confidence=0.72 if status == "resolved" else 0.55,
            source_refs=("llm_resolution",),
          )
        )

        if status != "partial":
          self._store.remove_pending(phrase)
        resolved += 1

    for item in data.get("known_revisions", []):
      phrase = str(item.get("phrase", "")).strip()
      if not phrase:
        continue
      should_update = bool(item.get("should_update", False))
      confidence = float(item.get("confidence", 0.0) or 0.0)
      if not should_update or confidence < self._config.revision_confidence_threshold:
        continue

      current = self._store.find_known_by_phrase(phrase)
      if current is None:
        continue

      tags = item.get("tags", [])
      self._store.upsert_known(
        JargonEntry(
          entry_id=current.entry_id,
          phrase=current.phrase,
          brief=str(item.get("brief", current.brief)).strip() or current.brief,
          details=str(item.get("details", current.details)).strip() or current.details,
          tags=tuple(tags) if isinstance(tags, list) and tags else current.tags,
          status=current.status,
          confidence=max(current.confidence, confidence),
          source_refs=current.source_refs + ("llm_revision",),
          version=current.version + 1,
          created_at=current.created_at,
        )
      )
      revised += 1

    if new_pending or resolved or revised:
      # Note: This is from LLM outputs
      new_pending_phrases = tuple(item.get("phrase", "") for item in data.get("new_pending", []))
      resolved_phrases = tuple(item.get("phrase", "") for item in data.get("resolved", []))
      self._decision_log.append(
        JargonDecision(
          new_pending_count=new_pending,
          new_pending_phrases=new_pending_phrases,
          resolved_count=resolved,
          resolved_phrases=resolved_phrases,
          revised_count=revised,
          notes="LLM 黑话判官结果已应用",
          analyzed_at=datetime.now(),
        )
      )

  def _apply_tag_output(self, data: dict) -> None:
    """应用标签判官结果"""
    for item in data.get("tag_updates", []):
      name = str(item.get("name", "")).strip()
      definition = str(item.get("definition", "")).strip()
      confidence = float(item.get("confidence", 0.0) or 0.0)
      if not name or not definition:
        continue
      if confidence < self._config.min_tag_confidence:
        continue

      examples = item.get("examples", [])
      related = item.get("related_tags", [])
      self._store.upsert_tag(
        TagEntry(
          name=name,
          definition=definition,
          examples=tuple(examples) if isinstance(examples, list) else tuple(),
          related_tags=tuple(related) if isinstance(related, list) else tuple(),
          confidence=confidence,
        )
      )

    suggestions = data.get("active_tag_suggestions", [])
    if isinstance(suggestions, list) and suggestions:
      tags = tuple(
        str(x).strip() for x in suggestions
        if str(x).strip()
      )
      if tags:
        self._rotate_active_tags_gradually(tags)

    hints = data.get("indirect_question_suggestions", [])
    if isinstance(hints, list):
      self._indirect_question_hints = tuple(
        str(x).strip() for x in hints if str(x).strip()
      )[:3]

  def _rotate_active_tags_gradually(self, suggested_tags: tuple[str, ...]) -> None:
    """按时间窗口每次仅替换一个 active tag，保持风格连续"""
    now = datetime.now()
    last_rotate_at = self._tag_state.last_rotate_at
    if last_rotate_at is not None:
      elapsed = (now - last_rotate_at).total_seconds()
      if elapsed < self._config.tag_rotation_interval_seconds:
        return

    unique_suggested: list[str] = []
    for tag in suggested_tags:
      if tag not in unique_suggested:
        unique_suggested.append(tag)

    if not unique_suggested:
      return

    current = list(self._tag_state.active_tags)
    if not current:
      current = ["普通网民"]

    max_count = max(1, self._config.active_tag_count)
    if len(current) > max_count:
      current = current[:max_count]

    # 若存在新标签，每次仅替换一个位置；否则保持不变
    replacement: Optional[str] = None
    for tag in unique_suggested:
      if tag not in current:
        replacement = tag
        break

    if replacement is None:
      return

    if len(current) < max_count:
      current.append(replacement)
      next_cursor = self._tag_state.rotation_cursor
    else:
      idx = self._tag_state.rotation_cursor % len(current)
      current[idx] = replacement
      next_cursor = (idx + 1) % len(current)

    self._tag_state = StreamerTagState(
      active_tags=tuple(current),
      candidate_tags=self._tag_state.candidate_tags,
      rotation_cursor=next_cursor,
      last_rotate_at=now,
    )

  def _learn_from_comments(self, comments: list["Comment"]) -> None:
    """从评论中提取疑似黑话并写入 pending"""
    if not comments:
      return

    new_pending_count = 0
    new_pending_phrases_list = []
    for comment in comments:
      candidates = extract_candidate_phrases(comment.content)
      for phrase in candidates:
        if self._store.find_known_by_phrase(phrase) is not None:
          continue

        pending = self._store.find_pending_by_phrase(phrase)
        if pending is not None:
          self._store.mark_pending_seen(phrase)
          continue

        self._store.upsert_pending(
          PendingJargon(
            phrase=phrase,
            candidate_brief="待观众解释的疑似黑话",
            candidate_tags=self._tag_state.active_tags,
            notes=f"初次发现于 {comment.nickname} 的弹幕",
            seen_count=1,
          )
        )
        new_pending_count += 1
        new_pending_phrases_list.append(phrase)

    if new_pending_count > 0:
      self._decision_log.append(
        JargonDecision(
          new_pending_count=new_pending_count,
          new_pending_phrases=tuple(new_pending_phrases_list),
          notes=f"新增待解明黑话 {new_pending_count} 条",
          analyzed_at=datetime.now(),
        )
      )

  def _promote_abandoned_pending(self) -> None:
    """将超过追问阈值的 pending 转为已知条目，避免重复追问"""
    promoted = 0
    promoted_phrases_list = []
    for pending in self._store.list_pending():
      if pending.asked_count < self._config.pending_abandon_threshold:
        continue

      removed = self._store.remove_pending(pending.phrase)
      if removed is None:
        continue

      self._store.upsert_known(
        JargonEntry(
          entry_id=f"jargon_{uuid.uuid4().hex[:12]}",
          phrase=removed.phrase,
          brief=removed.candidate_brief or "暂未获得明确解释",
          details=(
            "该表达在互动中多次追问仍未获得有效解释，"
            "暂按自然表达记录，用于避免重复追问。"
          ),
          tags=removed.candidate_tags or ("普通网民",),
          status="unresolved_resolved",
          confidence=0.35,
          source_refs=("pending_abandon",),
        )
      )
      promoted += 1
      promoted_phrases_list.append(removed.phrase)

    if promoted > 0:
      self._decision_log.append(
        JargonDecision(
          resolved_count=promoted,
          resolved_phrases=tuple(promoted_phrases_list),
          notes=f"放弃追问并转入已知条目 {promoted} 条",
          analyzed_at=datetime.now(),
        )
      )
