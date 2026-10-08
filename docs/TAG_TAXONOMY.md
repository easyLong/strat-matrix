# T1–T5 标签字典本地治理

依据《多账号智能策划_PRD_V1.0.docx》2.5.2 节。配置页维护 T1–T5；T6 仍由离线模型识别，不在此页编辑。

`GET /api/tag-taxonomy` 返回当前版本、启用标签名称 `tags`，以及包含稳定 `id`、`name`、`enabled` 的完整 `items`。页面使用 `items` 展示和修改；旧调用方仍可读取 `tags`。改名时提交同一 ID；停用只改变 `enabled`，不会删除该项。

```json
{
  "expected_version": 3,
  "items": {
    "T1": [{"id": "T1-EXISTING-ID", "name": "非营销", "enabled": true}],
    "T2": [{"id": "T2-EXISTING-ID", "name": "流量", "enabled": true}],
    "T3": [{"id": null, "name": "新标签", "enabled": true}],
    "T4": [{"id": "T4-EXISTING-ID", "name": "家庭客群", "enabled": true}],
    "T5": [{"id": "T5-EXISTING-ID", "name": "通勤", "enabled": true}]
  }
}
```

`PUT /api/tag-taxonomy` 要求提交五个维度的完整字典；新增项的 `id` 传 `null`，服务端分配 ID。各维度至少有一个启用项，名称不能重复。提交的 `expected_version` 与当前版本不同返回 409，页面需重新读取后再编辑。已存在 ID 即使从请求中缺席也会保留并停用；不支持物理删除。没有变化时不增加版本，也不产生事件。旧版 `{ "tags": { ... } }` 请求继续兼容：按同名复用 ID，新名称视作新增。

字典保存在 `godp_strategy_config`，每次实际变更同时写入 `godp_strategy_config_version` 快照，并记录 `TOPIC_TAXONOMY_CHANGED` 本地待投递事件。事件含当前启用名称和完整字典，尚未向客户系统主动投递。部署更新后运行 `cd backend && python3 -m app.init_db`，将既有名称数组原位迁移为带稳定 ID 的结构，不修改版本号；演示数据初始化不再覆盖已维护的字典。

旧页面曾把停用状态仅保存在当前浏览器。新页面首次读取时会将这些状态作为未保存草稿展示；运营核对后点击“保存标签配置”，状态才会进入服务端。已有服务端停用状态时，以服务端为准。

字典变更只影响之后新增普通选题的离线标签识别，不触发历史选题标签重算。

## 选题标签与字典版本关联

内部识别结果通过 `PUT /api/internal/topic-tags/{topic_id}` 写入。完成状态仍提交 T1–T6 单选名称，可以额外提交识别时使用的 `taxonomy_version`；省略时按当前字典版本解析。T1–T5 名称必须在该版本处于启用状态，服务端将其对应稳定 ID 与字典版本保存在选题标签记录中。T6 保留名称快照，不使用 T1–T5 字典 ID。

```json
{
  "label_status": "已完成",
  "taxonomy_version": 3,
  "tags": {
    "T1": ["非营销"], "T2": ["流量"], "T3": ["本地生活"],
    "T4": ["年轻客群"], "T5": ["周末休闲"], "T6": ["周末出行规划"]
  }
}
```

每次实际变更同时保存到 `godp_topic_tag_history`；重复提交完全相同的结果复用当前版本。`GET /api/internal/topic-tags/{topic_id}/history` 可用对接令牌查看逐版名称、稳定 ID、所用字典版本和识别状态。IF-08 对外查询仍仅返回 T1–T6 名称及状态，不改变客户接口契约；标签结果不主动推送。

部署更新后运行 `cd backend && python3 -m app.init_db`：为既有标签记录补充能从字典历史**唯一确定**的 T1–T5 ID，并把当前记录作为迁移基线写入历史表。无法唯一确定的旧名称保持原值、ID 留空；旧记录的准确识别字典版本未知时为 `null`。迁移无法恢复过去已被覆盖的标签版本。离线标签识别任务本身仍待开发。
