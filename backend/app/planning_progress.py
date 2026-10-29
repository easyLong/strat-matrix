"""Read content progress from current slot state or historical planning records."""

PRODUCTION_STATUS_SQL = (
    "COALESCE(NULLIF(s.production_status, ''), CASE "
    "WHEN i.status='已发布' THEN 'published' "
    "WHEN i.status IN ('已生成','生成完成','生产完成') THEN 'generated' "
    "WHEN i.status IN ('生成失败','生产失败','生产异常') THEN 'failed' "
    "WHEN i.status IN ('生成中','生产中') THEN 'ready' "
    "ELSE 'planned' END)"
)

COMPLETED_ACCOUNT_COUNT_SQL = (
    "COUNT(DISTINCT i.account_id) - COUNT(DISTINCT CASE "
    f"WHEN {PRODUCTION_STATUS_SQL} NOT IN ('generated','published') "
    "OR NULLIF(i.topic_id, '') IS NULL THEN i.account_id END)"
)


def production_status(row: dict) -> str:
    state = row.get("production_status")
    if state in ("planned", "ready", "generated", "published", "failed"):
        return state
    if row.get("published_at") or row.get("status") == "已发布":
        return "published"
    labels = {
        "已完成": "generated", "已生成": "generated", "生成完成": "generated", "生产完成": "generated",
        "已发布": "published",
        "生成失败": "failed", "生产失败": "failed", "生产异常": "failed",
        "生成中": "ready", "生产中": "ready", "上传中": "ready",
        "待生产": "planned", "待生成": "planned", "未生成": "planned",
    }
    return labels.get(state) or labels.get(row.get("status"), "planned")


def planning_status_label(status: str | None, failed_count: int = 0) -> str:
    if failed_count or any(marker in (status or "") for marker in ("失败", "异常", "错误")):
        return "生成失败"
    if status in ("已完成", "已规划", "待生成", "待生产", "已生成", "已发布"):
        return "已完成"
    if status in ("生成中", "生产中", "执行中", "进行中", "热点空槽待填充", "热点空槽待确定"):
        return "生成中"
    return "生成中"
