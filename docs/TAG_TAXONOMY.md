# T1–T5 标签字典本地治理

## 2026-10-18：分类展示与选题详情首轮升级

配置页已支持T3内容主题、T4目标客群、T5使用场景的“一级分类→二级标签”展示与编辑。默认只读，统一编辑及保存；可新增分类/叶子、改名、停用及移动叶子。T1/T2在此轮按现有固定值展示。

`items`新增可选字段：`node_type`（`group`分类或`tag`叶子）、`parent_id`（所属分类ID）。新增节点可提交`client_id`临时标识，服务端在同一次保存中分配正式ID并解析父子引用。分类本身不会进入旧版`tags`候选名称列表；父分类停用后，其后代不再作为可选标签。旧的平铺字典和已有标签ID继续兼容。

部署首次升级可在backend目录执行 `python -m app.upgrade_tag_taxonomy`。初始化使用 `frontend/src/data/topicTaxonomy.json` 中20个建议分类、127个叶子，已有标签保留原ID；无法按名称准确归类的放入“待归类”。已有分类树时重复执行不修改数据。初始化通过正常版本化保存留痕，不重写历史选题识别结果。

新增运营页面读取接口 `GET /api/topics/{topic_id}/detail?topic_type=普通`，提供标题、大纲、有效期、已有标签及其状态/版本；类型参数可区分普通、营销、热点来源，同ID多来源且未指定类型时返回409。它不触发识别。

`GET /api/topics` 和替换候选列表附带已保存标签，供共用级联组件筛选。详情兼容旧单值结果和新结构化结果；缺失内容显示未识别，不用标题猜标签。该轮尚未改变正式标签写入、画像、向量及算法契约，后续按[升级方案](选题标签体系升级完整方案_V1.0_评审稿.md)推进。

下面保留原有单选识别链路说明，分类字段以本节为补充。

依据《多账号智能策划_PRD_V1.1_近期口径同步稿.docx》2.5.2 节。配置页维护 T1–T5；T6 仍由离线模型识别，不在此页编辑。

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

内部识别结果通过 `PUT /api/internal/topic-tags/{topic_id}` 写入。完成状态仍提交 T1–T6 单选名称；已领取的任务必须附带 `lease_id` 和领取时锁定的 `taxonomy_version`，没有任务的旧调用方省略版本时按当前字典版本解析。T1–T5 名称必须在该版本处于启用状态，服务端将其对应稳定 ID 与字典版本保存在选题标签记录中。新的已完成结果还须提交 `t6_embedding` 和 `t6_embedding_model`，由服务端复用或创建 T6 稳定 ID；T6 不使用 T1–T5 字典 ID。

```json
{
  "label_status": "已完成",
  "lease_id": "CLAIM-LEASE-ID",
  "taxonomy_version": 3,
  "tags": {
    "T1": ["非营销"], "T2": ["流量"], "T3": ["本地生活"],
    "T4": ["年轻客群"], "T5": ["周末休闲"], "T6": ["周末出行规划"]
  },
  "t6_embedding_model": "your-embedding-model-version",
  "t6_embedding": [0.12, 0.34, 0.56]
}
```

每次实际变更同时保存到 `godp_topic_tag_history`；重复提交完全相同的结果复用当前版本。`GET /api/internal/topic-tags/{topic_id}/history` 可用对接令牌查看逐版名称、T1–T5 稳定 ID、T6 稳定 ID、所用字典版本和识别状态。IF-08 对外查询仍仅返回 T1–T6 名称及状态，不改变客户接口契约；标签结果不主动推送。

部署更新后运行 `cd backend && python3 -m app.init_db`：为既有标签记录补充能从字典历史**唯一确定**的 T1–T5 ID，并把当前记录作为迁移基线写入历史表。无法唯一确定的旧名称保持原值、ID 留空；旧记录的准确识别字典版本未知时为 `null`。既有 T6 按名称补稳定 ID，但历史向量无法恢复。迁移无法恢复过去已被覆盖的标签版本。首次识别任务的领取与回写见[普通选题首次标签识别任务](TOPIC_LABEL_JOBS.md)。
