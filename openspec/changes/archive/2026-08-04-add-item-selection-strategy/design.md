## Context

分析引擎 `src/app/backend/services/analysis/engine.py` 在非自定义模式下，对每个绑定信息源构造候选条目查询（行 107–156）：

```python
q = db.query(InfoItem).filter(InfoItem.source_id == ts.source_id)
if mode == "incremental" and ts.last_analyzed_item_id:
    q = q.filter(InfoItem.id > ts.last_analyzed_item_id)      # 位置水位线
items = q.order_by(InfoItem.id.asc()).limit(max_per).all()    # 按 id 升序取最旧
```

即「按入库 `id` 升序、水位线之后取最旧篇」。分析后置 `it.analyzed = True`（行 103/135/151）并推进 `ts.last_analyzed_item_id = items[-1].id`（行 154）。自定义模式（`custom`）走独立分支（行 72–105），不受影响。

`InfoItem`（`models/info_source.py`）已具备时间字段 `published_at`（FreshRSS 取 feed published、local_folder 取文件 mtime、website 不设置）、`article_published_at`（PDF/docx/html 文档元数据发布时间）、`fetched_at`（抓取入库时间），以及 `analyzed` 状态字段。同步服务在内容变更（`content_hash` 变化）时已将 `analyzed` 重置为 `False`（`services/info_source/sync.py`），故 `analyzed` 状态可作为「是否已分析」的可靠依据。

`AnalysisTask.config` 为自由 JSON（`schemas/analysis.py` 的 `AnalysisTaskCreate.config: dict`），已承载 `mode`/`max_items_per_source`/`system_prompt`/`user_prompt_template`/`custom_item_ids`/`model` 等字段，是天然扩展点。前端 `AnalysisTasks.vue` 表单已有 `mode` 下拉与「高级配置 JSON」textarea（`configText`），保存时 `config = JSON.parse(configText)` 再用下拉值覆盖 `config.mode`（行 261–278）。

定时调度（APScheduler，`services/scheduler.py`）与邮件推送（`services/push/`，`on_analysis_completed` 钩子）已端到端就绪，不在本变更代码范围。约束（CLAUDE.md）：不硬编码环境信息；时间显示北京时间；优先 SQLite/Python/FastAPI+Vue；无新依赖；`data` 目录不入 `.gitignore`。

## Goals / Non-Goals

**Goals:**
- 新增 `selection_strategy` 任务级配置（`sequential` / `newest_unanalyzed`），`newest_unanalyzed` 按「未分析 + 时间倒序」选取最新 N 篇。
- `sequential` 为默认且行为与现状完全一致（向后兼容）。
- `newest_unanalyzed` 的时间排序键覆盖所有信息源类型（`published_at` -> `article_published_at` -> `fetched_at`）。
- 前端表单提供下拉配置，与既有「高级配置 JSON」兼容。
- 文档补全选择策略说明与「每日定时分析最新文章 + 邮件推送」端到端配置指引。

**Non-Goals:**
- 不改动定时调度与邮件推送代码（已具备，通过配置串联）。
- 不改动自定义模式（`custom`）的候选与运行语义。
- 不改动 `InfoItem` 数据模型与同步逻辑（复用既有 `analyzed` 字段与同步重置行为）。
- 不引入「随机选取」「按权重选取」等其他策略；不做策略组合。
- 不改动 `InfoSources.vue` / `item-selection-modal` 弹窗（与本后端策略正交）。

## Decisions

### 决策 1：策略存于 `config.selection_strategy`，不新增数据模型字段
`selection_strategy` 作为 `AnalysisTask.config` JSON 的一个可选键传递，不新增数据库列、不新增表、不新增 API 签名。
**理由**：`config: dict` 已是既有扩展点（`mode`/`max_items_per_source` 等均如此），最小改动面，存量任务无 `selection_strategy` 即回退默认。
**备选**：为 `AnalysisTask` 新增显式 `selection_strategy` 列 -> 否（需迁移、改 schema/API，过度工程）。

### 决策 2：`newest_unanalyzed` 以 `analyzed == False` 为候选依据，不使用水位线筛选
候选查询为 `filter(analyzed == False)` + 时间倒序 + `limit(max_per)`；`last_analyzed_item_id` 仅在分析后更新用于监控展示，不进入筛选条件。
**理由**：水位线语义是「顺序推进至某 id」，与「跨 id 选最新」相互冲突；`analyzed` 状态字段已存在且同步时正确重置，是「是否已分析」的天然依据。每次选最新一篇、分析后置 `analyzed=True`，下次自动跳过，逻辑自洽。
**备选**：保留水位线并改为 `id < last_analyzed_item_id order by id desc` -> 否（仍依赖入库顺序而非文章时间，且水位线语义被扭曲）。

### 决策 3：时间排序键 `COALESCE(published_at, article_published_at, fetched_at)` 降序，次级 `id` 降序
SQLAlchemy 以 `func.coalesce(InfoItem.published_at, InfoItem.article_published_at, InfoItem.fetched_at).desc()` 为排序主键，`InfoItem.id.desc()` 为次级排序。
**理由**：`published_at` 是「文章时间/文件修改时间」的最直接体现；website 源无 `published_at`，需回退 `article_published_at`（文档元数据）再回退 `fetched_at`（入库时间），否则 website 条目全部 NULL 无法排序。次级 `id` 降序保证时间相同时结果稳定可预期。
**备选**：仅用 `published_at` -> 否（website 源失效）；仅用 `fetched_at` -> 否（不反映文章自身时间，与需求「文章时间」不符）。

### 决策 4：`newest_unanalyzed` 在 `full` 与 `incremental` 模式下候选集一致
两种触发模式下候选集均为 `analyzed == False` + 时间倒序 + `limit(max_per)`。
**理由**：策略语义是「选最新未分析」，与触发模式无关；`full` 本就受 `max_items_per_source` 限制（非真正全量），统一行为减少分支与歧义。
**备选**：仅 `incremental` 生效、`full` 仍取全部 -> 否（同一任务两种模式候选口径不一致，易混淆）。

### 决策 5：`newest_unanalyzed` 下仍更新 `last_analyzed_item_id` / `last_analyzed_at`
分析完成后将 `ts.last_analyzed_item_id` 设为本批最大 `id`、`last_analyzed_at` 设为当前时间，与 `sequential` 保持字段语义一致，供 `TaskSourceOut` 与任务中心监控展示。
**理由**：监控字段不应因策略不同而断裂；字段存在但不参与筛选（决策 2），无副作用。
**备选**：`newest_unanalyzed` 下不更新水位线 -> 否（监控展示断裂，字段语义不一致）。

### 决策 6：未知策略值回退 `sequential` 而非报错
`config.selection_strategy` 取值不在 `{sequential, newest_unanalyzed}` 时回退默认，记录日志，不中断。
**理由**：容错优先，与既有 `sort_by` 白名单回退（`item-selection-modal`）风格一致；存量任务或手写 JSON 笔误不应导致分析失败。
**备选**：未知值报错 -> 否（降低健壮性）。

### 决策 7：前端下拉值保存时覆盖 JSON 同名键（同 `mode` 处理）
`buildConfig` 时执行 `config.selection_strategy = form.selectionStrategy`，与现有 `config.mode = form.mode` 一致；编辑时 `form.selectionStrategy = t.config?.selection_strategy || 'sequential'` 回填。
**理由**：下拉为主配置入口、可预测；同时保留「高级配置 JSON」对其他字段的灵活性。与既有 `mode` 处理路径完全对称，降低认知成本。
**备选**：仅支持 JSON 手写 -> 否（用户配置每日任务时不友好）；JSON 优先于下拉 -> 否（两入口冲突、行为不可预测）。

### 决策 8：不引入新依赖，沿用 SQLAlchemy `func.coalesce`
排序用 SQLAlchemy 内置 `func.coalesce`，SQLite 原生支持 `COALESCE`。
**理由**：符合无新依赖约束；与既有查询风格一致。
**备选**：应用层排序 -> 否（破坏跨分页一致性、`limit` 失真）。

## Risks / Trade-offs

- **`analyzed` 状态准确性依赖同步逻辑** -> 既有 `sync.py` 已在 `content_hash` 变更时重置 `analyzed=False`；本变更复用该行为，单测覆盖「内容变更后可被重新选中」。
- **website 源时间字段可能全空** -> `COALESCE` 最终回退 `fetched_at`（抓取必入库，非空）；极端全空时 `id` 降序兜底，结果仍稳定。
- **`newest_unanalyzed` + 大量未分析条目** -> 受 `max_items_per_source` 限制（默认 50，用户场景设 1），`limit` 在 SQL 层完成，无性能问题。
- **策略切换语义** -> 任务从 `sequential` 切到 `newest_unanalyzed`：历史已分析篇因 `analyzed=True` 不会被重复选取；反向切换：`sequential` 按水位线推进，已分析篇水位线已越过，不重复。两种切换均安全。
- **`full` 模式语义在 `newest_unanalyzed` 下不再是「取全部」** -> 文档明确说明；默认 `sequential` 不变，存量任务不受影响。
- **多源任务每源各选最新** -> 符合预期（每个绑定源独立选其最新未分析篇）；`max_items_per_source` 按源生效，与现状一致。

## Migration Plan

1. **后端（测试先行）**：在 `engine.py` 将候选查询构造按 `selection_strategy` 分流--`sequential` 走原代码路径（不改一行）；`newest_unanalyzed` 新增 `filter(analyzed == False)` + `func.coalesce(...).desc()` + `id.desc()` + `limit(max_per)` 分支，分析后更新水位线但不用于筛选。未知值回退 `sequential` 并记日志。单测覆盖各策略与时间优先级。
2. **前端**：`AnalysisTasks.vue` 表单新增「条目选择策略」下拉与 `form.selectionStrategy` 状态；`buildConfig` 合并 `config.selection_strategy`；`editTask` 回填；`npm run build` 冒烟 + 手工验证。
3. **文档**：更新 `README.md`、需求规格说明书、设计说明书--补充选择策略字段说明与「每日定时分析最新文章 + 邮件推送」端到端配置指引（信息源同步 -> 分析任务设 `newest_unanalyzed` + `max_items_per_source=1` -> 定时任务 cron -> 推送规则 `on_run`）。
4. **Jenkinsfile**：无依赖/启动变化，不动；提交 Github 后手工触发构建并由用户验证。
5. **回滚**：`selection_strategy` 为 `config` 可选键；删除 `engine.py` 新增分支即回退到 `sequential`；前端下拉缺省 `sequential`，存量任务不受影响。

## Open Questions

- 是否在任务卡片/任务中心以 pill 展示当前策略（与 `mode` pill 同列）？建议作为可选增强，非本次阻塞项。
- `newest_unanalyzed` 是否需要「跳过最近 N 小时刚抓取条目」以防内容尚未稳定？暂不做，后续可作为 `selection_strategy` 的附加配置（如 `min_age_hours`）。
