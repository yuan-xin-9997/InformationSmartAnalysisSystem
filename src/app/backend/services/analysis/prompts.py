"""Default analysis prompt templates (overridable per task via task.config)."""
from __future__ import annotations

DEFAULT_SYSTEM_PROMPT = (
    "你是一个专业的信息分析助手。请基于用户提供的信息内容进行结构化分析，"
    "输出：1) 关键要点；2) 主题分类；3) 潜在风险或趋势。语言简洁、条理清晰。"
)

DEFAULT_PER_ITEM_TEMPLATE = (
    "请对以下信息进行分析，输出关键要点、主题与简要结论：\n\n"
    "标题：{title}\n\n内容：\n{content}"
)

DEFAULT_AGGREGATE_TEMPLATE = (
    "以下是一批信息条目，请综合分析其共同主题、关键事件、趋势与风险，"
    "输出一份综合分析报告：\n\n{items}"
)


def render_per_item(system_prompt: str, user_template: str, item) -> tuple[str, str]:
    system = system_prompt or DEFAULT_SYSTEM_PROMPT
    tpl = user_template or DEFAULT_PER_ITEM_TEMPLATE
    user = tpl.format(title=item.title or "(无标题)", content=item.content or "(无内容)")
    return system, user


def render_aggregate(system_prompt: str, user_template: str, items) -> tuple[str, str]:
    system = system_prompt or DEFAULT_SYSTEM_PROMPT
    tpl = user_template or DEFAULT_AGGREGATE_TEMPLATE
    body = "\n\n---\n\n".join(
        f"标题：{it.title or '(无标题)'}\n内容：{it.content or '(无内容)'}" for it in items
    )
    user = tpl.format(items=body)
    return system, user
