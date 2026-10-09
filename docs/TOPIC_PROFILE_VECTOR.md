# 普通选题画像与向量准备

依据《多账号智能策划_PRD_V1.0.docx》3.4.5–3.4.6 节。普通选题完成首次 T1–T6 标签识别后，服务端从**当前有效内容**和已保存标签生成画像。画像包含标题、摘要、大纲、内容类型、分类、来源、产品或活动、适用城市与 T1–T6 单选标签。画像 JSON 经规范化后计算 SHA256 `content_hash`；热度、审核状态、有效期和来源更新时间不参与语义指纹。

画像与向量状态保存在 `godp_topic_profile`。同一选题当前只保存一版画像：当画像字段或标签结果变化时，更新指纹和 `tag_version`，清空旧向量并转为 `pending`。同步仅改变热度等非画像字段时，已有向量保持有效。后续选题编辑**不会重算 T1–T6**。全量快照停用、目录停用或有效期外的选题不进入准备任务和 AI 候选查询；重新变为可用时，如画像内容未变化，可继续使用原有效向量。

部署更新后先运行：

```bash
cd backend
python3 -m app.init_db
```

迁移会为已有正式普通选题中标签完整的记录生成当前画像；没有向量的记录处于 `pending`，不会伪造已就绪状态。新表和每个字段均有中文说明。

## 内部接口

下列接口都要求 `X-Integration-Token`，属于**项目内部向量准备接口**，不是客户选题库接口。

| 接口 | 用途 |
| --- | --- |
| `GET /api/internal/topic-profiles/{topic_id}` | 查询单个选题的准备状态：`awaiting_labels`、`label_failed`、`pending`、`failed`、`ready`、`stale` 或 `unavailable`。 |
| `GET /api/internal/topic-vector-jobs?limit=100&after_id=0` | 分页读取待生成或失败待重试的当前画像。响应包含 `next_after_id`、`topic_id`、`content_hash`、`tag_version` 和 `profile`。 |
| `PUT /api/internal/topic-vectors/{topic_id}` | 写入该画像的向量或失败原因。请求必须带读取时的 `content_hash` 和 `tag_version`；过期结果返回 409。 |
| `GET /api/internal/ai-topic-candidates?limit=100&after_id=0` | 分页读取标签、当前画像和向量均有效的正式普通选题，返回画像与向量；其他选题不会出现在候选中。 |

向量成功回写示例：

```json
{
  "content_hash": "64位小写SHA256指纹",
  "tag_version": 1,
  "status": "ready",
  "vector_model": "your-topic-embedding-model-version",
  "vector": [0.12, 0.34, 0.56]
}
```

上例中 `content_hash` 须替换为任务接口返回的真实值；三维数字只演示协议格式。向量须为 1–4096 维有效非零数值，服务端保存单位向量。失败回写使用同一接口，提交 `status="failed"`、`error`、`content_hash` 和 `tag_version`，不提交 `vector` 和 `vector_model`。失败任务可再次领取。当前版本没有向量服务的具体接入地址，因此只提供项目内部准备状态和回写契约，**不会自动生成或伪造向量**。

当前任务列表没有租约，多个向量进程可能读取同一任务；同一画像先写入的已就绪向量获胜，后续完全相同的回写可幂等返回，不同向量返回 409。内容或标签更新后旧指纹失效，旧结果无法写入。任务列表和 `ai-topic-candidates` 读取时再次核对当前内容指纹，避免过期画像进入后续 AI 匹配。分页时始终使用响应的 `next_after_id` 继续查询，即使当前页因过期记录被过滤后为空。当前正式周策划仍使用普通选题热度规则兜底，尚未读取这个 AI 候选接口，也尚未运行账号画像、Recall、Fit 或全局分配。
