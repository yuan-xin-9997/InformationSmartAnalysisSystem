## 1. 数据模型与迁移

- [ ] 1.1 在 `src/app/backend/models/info_source.py` 的 `InfoItem` 增加可空列 `author`、`author_affiliation`、`article_published_at`、`page_count`
- [ ] 1.2 新建 `InfoItemFigure` 模型（`item_id` 外键级联删除、`figure_index`、`storage_path`、`mime`、`width`、`height`、`caption`、`created_at`），在 `models/__init__.py` 注册
- [ ] 1.3 在 `core/db.py`（或现有初始化处）启动时对已存在的 `info_items` 表执行 `ALTER TABLE ADD COLUMN` 补列；确认 `create_all` 能建出 `info_item_figures`
- [ ] 1.4 编写测试：新列默认值为空、`InfoItemFigure` 随 `InfoItem` 删除级联（测试先行）

## 2. 配置

- [ ] 2.1 在 `src/app/backend/core/config.py` 的 `Settings` 增加 `figures_dir`（默认 `data/figures`）、`max_figures_per_item`（默认 20），支持 `ISAS_FIGURES_DIR`/`ISAS_MAX_FIGURES_PER_ITEM` 环境变量覆盖
- [ ] 2.2 在 `src/config/app.json` 增加对应默认段；在 `src/app/backend/main.py` 启动时创建图表目录
- [ ] 2.3 编写测试：配置解析与 env 覆盖（测试先行）

## 3. 元数据抽取

- [ ] 3.1 在 `src/app/backend/services/info_source/local_folder.py` 新增 `extract_metadata(path)`：PDF 用 `fitz` `doc.metadata` + `doc.page_count`、docx 用 `core_properties`、HTML 用 `<title>`/`<meta>`，返回 `{title, author, published_at, page_count}`
- [ ] 3.2 新增 `extract_author_affiliation(first_page_text)`：按机构关键词正则（`大学|学院|研究所|研究院|公司|实验室|医院|Department|University|Institute|Lab|College` 等）匹配行，命中取该行、无命中返回 `None`
- [ ] 3.3 在 `fetch_new_items()` 抽取时调用上述方法写入 `InfoItem` 对应字段；标题为空时回退文件名
- [ ] 3.4 编写测试：PDF 文档属性抽取、作者单位命中与留空、txt/md 回退文件名（测试先行）

## 4. 图表抽取与落盘

- [ ] 4.1 在 `local_folder.py` 新增 `extract_figures(path, item_id, figures_dir)`：PDF 用 `page.get_images()` + `doc.extract_image(xref)`、docx 遍历 `document.part.rels` 中 `image/*` 关系取字节；按 `figures_dir/YYYY/MM/DD/{item_id}_{index}.{ext}` 落盘
- [ ] 4.2 宽高从 PNG/JPEG 头字节解析，失败留空；超过 `max_figures_per_item` 截断并记日志
- [ ] 4.3 落盘后批量写 `InfoItemFigure` 记录（`figure_index`/`storage_path`/`mime`/`width`/`height`）
- [ ] 4.4 编写测试：PDF 多图落盘与记录、无图不建记录、超上限截断（测试先行）

## 5. 存量回填与手动重新抽取

- [ ] 5.1 改 `fetch_new_items()`：`content_hash` 未变但缺元数据/图表时补抽并 upsert
- [ ] 5.2 新增 `reextract_item(source_id, item_id)` 服务：清理旧图表记录与旧图文件、重抽元数据 + 图表、更新 `InfoItem` 并返回最新结果
- [ ] 5.3 编写测试：存量补齐、`reextract` 幂等、旧图表文件清理（测试先行）

## 6. Schema 扩展

- [ ] 6.1 在 `src/app/backend/schemas/info_source.py` 增加 `InfoItemFigureOut`、`SourceFileOut`（`filename`/`file_path`/`title`/`author`/`author_affiliation`/`published_at`/`page_count`/`figures`）
- [ ] 6.2 在 `src/app/backend/schemas/analysis.py` 的 `AnalysisResultOut` 增加可空字段 `source_file: SourceFileOut | None`
- [ ] 6.3 编写测试：schema 序列化--`per_item` 含 `source_file`、`aggregate` 为 `null`（测试先行）

## 7. 结果 API 扩展

- [ ] 7.1 改 `src/app/backend/api/analysis_tasks.py` 的 results 查询：批量预取相关 `InfoItem` 与 `InfoItemFigure`，组装 `source_file`，避免 N+1
- [ ] 7.2 编写测试：`per_item` 返回文件信息与图表列表、`aggregate` 为空、单次取数即可渲染（测试先行）

## 8. 文件预览与图表服务接口（含安全）

- [ ] 8.1 在 `src/app/backend/api/info_sources.py` 新增 `GET /{source_id}/items/{item_id}/file`：按 `InfoItem` 归属解析路径并校验位于源 `config.folder_path` 之下；PDF `inline` 返回、HTML/txt/md 以文本返回、docx `attachment` 下载
- [ ] 8.2 新增 `GET /{source_id}/items/{item_id}/figures/{index}`：按归属与序号返回图表字节 + 正确 MIME
- [ ] 8.3 新增 `POST /{source_id}/items/{item_id}/reextract`：调用 `reextract_item`，返回最新结果
- [ ] 8.4 编写测试：PDF `inline`、docx 下载、路径穿越/跨源返回 403/404、磁盘缺失 404、图表按序号获取（测试先行）

## 9. 前端结果页三段式与预览

- [ ] 9.1 在 `src/app/frontend/src/api/tasks.ts` 与 `src/app/frontend/src/api/sources.ts` 扩展类型：`AnalysisResultOut.source_file`、`SourceFileOut`、`InfoItemFigureOut`，及 file/figure/reextract 调用函数
- [ ] 9.2 重建 `src/app/frontend/src/views/TaskResults.vue` 的 `per_item` 结果卡片为三段式：① 文件信息（文件名可点击 + 文件路径）；② 文章基本信息（标题/作者/作者单位/发布时间/页数）+ 图表缩略图；③ 文字分析结果（markdown 渲染）；`aggregate` 保持仅文字
- [ ] 9.3 新增文件预览弹层：PDF 用 `iframe` 内嵌预览、HTML/txt/md 直接渲染、docx 下载按钮 + 已抽取纯文本预览
- [ ] 9.4 新增图表画廊：缩略图点击查看大图
- [ ] 9.5 展示时间为北京时间；沿用 `src/app/frontend/src/style.css` 自定义样式（无 UI 库）
- [ ] 9.6 冒烟测试：`npm run build` 通过；手工验证三段式展示、文件预览、图表查看

## 10. 文档与部署

- [ ] 10.1 更新 `README.md`（结果页三段式说明、新接口、`figures_dir`/`max_figures_per_item` 配置项）
- [ ] 10.2 更新需求规格说明书、设计说明书
- [ ] 10.3 Jenkinsfile 无依赖/启动变化则不动，否则同步更新
- [ ] 10.4 部署后对现有 `local_folder` 源触发一次同步或手动 `reextract` 补齐存量；手工触发 Jenkins 构建并由用户验证
