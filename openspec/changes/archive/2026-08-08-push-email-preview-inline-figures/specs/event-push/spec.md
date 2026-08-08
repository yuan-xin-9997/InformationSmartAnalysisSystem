## ADDED Requirements

### Requirement: 邮件正文内嵌图表

系统 SHALL 在推送 `per_item` 事件时，把该事件关联的图表图片以 `Content-ID`（CID）方式内嵌进邮件 HTML 正文：正文相应位置渲染为 `<img src="cid:<cid>">`，图表字节作为 `multipart/mixed` 的内联图片 MIME 部分（`Content-Disposition: inline`，带 `Content-ID` 头）随邮件一并发出，使邮件客户端无需回访任何外部接口即可直接显示图表。图表字节 MUST 复用「邮件附件」同一来源（`InfoItemFigure.storage_path`，经 `figures_dir` 路径校验），不引入新的读取路径。每个图表 MUST 拥有唯一的 CID。内嵌图表 MUST 与图表附件共存（图表既在正文显示、又作为附件可下载）。`aggregate` 事件无图表，正文 MUST NOT 出现图表。`per_item` 事件无图表时，正文 MUST NOT 出现空占位或破损图片标记。图表读取失败（文件不存在、路径越界、超大小上限）时 MUST 跳过该图表的内嵌（与附件跳过语义一致），不中断推送。

#### Scenario: per_item 事件正文内嵌图表

- **WHEN** 推送一个 `per_item` 事件，其关联 `InfoItem` 有 2 张图表且文件可读
- **THEN** 邮件 HTML 正文在分析结果后渲染 2 个 `<img src="cid:...">`，邮件附带 2 个内联图片 MIME 部分（各带唯一 `Content-ID`），邮件客户端打开即可直接看到这 2 张图表

#### Scenario: 图表同时作为附件

- **WHEN** 一个 `per_item` 事件的图表被内嵌进正文
- **THEN** 该图表同时作为邮件附件（`Content-Disposition: attachment`）发送，收件人可下载

#### Scenario: 无图表的 per_item 事件不出现占位

- **WHEN** 推送一个 `per_item` 事件但其 `InfoItem` 无图表
- **THEN** 邮件正文不出现 `<img>` 标记或破损图片占位，邮件正常发送

#### Scenario: aggregate 事件不内嵌图表

- **WHEN** 推送一个 `aggregate` 事件
- **THEN** 邮件正文不含任何内嵌图表

#### Scenario: 图表读取失败时跳过内嵌

- **WHEN** 一个图表文件不存在或路径越界
- **THEN** 系统跳过该图表的内嵌（也不作为附件），记日志，其余图表正常内嵌，推送不中断

### Requirement: 邮件内容留存与预览

系统 MUST 在每次推送执行发送邮件后，把该次实际渲染并发送的邮件内容留存到推送历史：包括邮件主题、HTML 正文（内嵌图表随正文一并留存，可在预览中直接显示）、附件清单（原文件名与图表文件名，以及被跳过附件的摘要）。当一次推送因事件数超过每邮件上限而分多批发送多封邮件时，系统 MUST 留存各批邮件内容（可合并展示）。系统 SHALL 在「任务分析」页推送历史中，对至少成功发出 1 封邮件的记录提供「预览」入口，点击后以与邮件一致的形式渲染该邮件 HTML（含内嵌图表）。预览 MUST 仅对拥有 `analysis_tasks` 页面权限的用户可用。未发出邮件的记录（`no_new`、或发送前失败的 `failed`）MUST NOT 提供预览。

#### Scenario: 成功推送留存邮件内容

- **WHEN** 一次推送成功发送了含 2 个 `per_item` 事件（各 1 张图表）的邮件
- **THEN** 该推送历史记录留存邮件主题、HTML 正文（含 2 张内嵌图表，可在预览中直接显示）与附件清单（2 个图表文件名），执行时间以北京时间显示

#### Scenario: 推送历史预览邮件内容

- **WHEN** 管理员在推送历史中对一条已成功发送的记录点击「预览」
- **THEN** 系统弹出预览层，以与邮件一致的形式渲染该邮件 HTML，内嵌图表直接可见

#### Scenario: 多批邮件合并预览

- **WHEN** 一次推送分 2 批发送了 2 封邮件，管理员点击该记录「预览」
- **THEN** 预览层依次展示 2 封邮件的内容（各含其主题、正文、图表）

#### Scenario: 未发送邮件的记录不可预览

- **WHEN** 管理员对一条状态为 `no_new`（无新事件）的推送记录操作
- **THEN** 该记录不提供「预览」入口

#### Scenario: 预览受页面权限保护

- **WHEN** 未被授予 `analysis_tasks` 页面权限的用户调用预览接口
- **THEN** 系统拒绝访问（前端不展示入口、后端返回 403）
