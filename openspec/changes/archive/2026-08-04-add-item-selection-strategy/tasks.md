## 1. 后端：条目选择策略实现（测试先行）

- [x] 1.1 编写测试：`engine` 未指定 `selection_strategy` 时按 `sequential` 运行（增量按 `id > 水位线` 升序取、全量取全部、分析后推进水位线）--回归保护
- [x] 1.2 编写测试：`selection_strategy=newest_unanalyzed` 选取 `analyzed == False` 中时间最新的条目（`published_at` 优先），已分析篇被跳过
- [x] 1.3 编写测试：`newest_unanalyzed` 时间键优先级 `published_at` -> `article_published_at` -> `fetched_at`；时间键相同或均空时按 `id` 降序稳定排序
- [x] 1.4 编写测试：`newest_unanalyzed` 下 `max_items_per_source` 限制选取数量、多源各自独立选取；分析后 `analyzed=True` 且 `last_analyzed_item_id`/`last_analyzed_at` 更新，但下次候选不依据水位线（`id < 水位线` 的未分析篇仍可被选）
- [x] 1.5 编写测试：未知 `selection_strategy` 值回退 `sequential` 不报错；`custom` 模式不受策略影响（仍分析 `custom_item_ids`）
- [x] 1.6 在 `src/app/backend/services/analysis/engine.py` 实现策略分流：`sequential` 走原代码路径不变；`newest_unanalyzed` 新增 `filter(InfoItem.analyzed.is_(False))` + `func.coalesce(published_at, article_published_at, fetched_at).desc()` + `InfoItem.id.desc()` + `limit(max_per)` 分支；分析后更新水位线但不用于筛选；未知值回退 `sequential` 并记日志

## 2. 前端：选择策略下拉

- [x] 2.1 在 `src/app/frontend/src/views/AnalysisTasks.vue` 表单新增 `form.selectionStrategy` 状态与「条目选择策略」下拉（顺序分析 / 最新未分析优先）
- [x] 2.2 `buildConfig` 保存时写入 `config.selection_strategy = form.selectionStrategy`（覆盖「高级配置 JSON」同名键）；`editTask` 从 `config.selection_strategy` 回填，缺省 `sequential`
- [x] 2.3 `resetForm` 重置 `selectionStrategy` 为 `sequential`
- [x] 2.4 `npm run build` 冒烟通过（vue-tsc 类型检查 + vite build 均通过）；手工验证下拉选择保存、编辑回填、与高级配置 JSON 共存

## 3. 文档与部署

- [x] 3.1 更新 `README.md`：分析任务「条目选择策略」字段说明 + 「每日定时分析最新文章 + 邮件推送」端到端配置指引（信息源同步 -> 分析任务设 `newest_unanalyzed` + `max_items_per_source=1` -> 定时任务 cron -> 推送规则 `on_run`）
- [x] 3.2 更新需求规格说明书、设计说明书（选择策略需求与设计）
- [x] 3.3 运行后端全量测试通过
- [x] 3.4 `Jenkinsfile` 无依赖/启动变化则不动；提交 Github 后手工触发 Jenkins 构建并由用户验证新增功能
