## ADDED Requirements

### Requirement: 邮件附件

系统 SHALL 在推送 `per_item` 事件时，把文章原文件与内嵌图表图片作为邮件附件一并发送。原文件附件仅对 `local_folder` 源生效（从 `InfoItem.external_id` 读取）；`website`/`freshrss` 源无原文件附件。图表附件从 `InfoItemFigure.storage_path` 读取。附件读取 MUST 复用文件服务的路径校验（原文件 `is_relative_to` 源 `folder_path`、图表 `is_relative_to` `figures_dir`）防路径穿越。`aggregate` 事件无附件。单文件超过大小上限（默认 10MB）时 MUST 跳过该附件并记日志，不中断推送；文件不存在或路径越界时 MUST 跳过该附件。

#### Scenario: per_item 事件附带原文件与图表附件
- **WHEN** 推送一个 `per_item` 事件，其关联 `InfoItem` 属于 `local_folder` 源且有原文件与 2 张图表
- **THEN** 邮件附带原文件附件与 2 张图表图片附件

#### Scenario: 非 local_folder 源不附原文件
- **WHEN** 推送一个 `per_item` 事件，其信息源为 `website` 或 `freshrss`
- **THEN** 邮件不附带原文件附件（图表若存在仍附带）

#### Scenario: 路径越界的文件不被附加
- **WHEN** 附件文件路径经解析后不在源 `folder_path` 或 `figures_dir` 范围内
- **THEN** 系统跳过该附件（不读取、不附加），不报错

#### Scenario: 超大小上限的附件被跳过
- **WHEN** 某附件文件大小超过上限（如 10MB）
- **THEN** 系统跳过该附件并记日志，其余附件正常发送，推送不中断

#### Scenario: aggregate 事件无附件
- **WHEN** 推送一个 `aggregate` 事件
- **THEN** 邮件不附带任何附件
