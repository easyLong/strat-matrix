"""Populate organization, platform, and lifecycle source data for demo accounts."""

import json
from datetime import datetime, timezone

from .db import connection
from .demo_account_data import demo_account_dimensions
from .models import StrategyConfig


def main() -> None:
    updated = 0
    now = datetime.now(timezone.utc)
    with connection() as db, db.cursor() as cursor:
        cursor.execute(
            "SELECT config_json FROM godp_strategy_config "
            "WHERE config_key='operations' AND del_flag='N' ORDER BY version DESC LIMIT 1"
        )
        config_row = cursor.fetchone()
        if not config_row:
            raise RuntimeError("未找到有效的账号生命周期配置")
        config = StrategyConfig.model_validate_json(config_row["config_json"])
        cursor.execute(
            "SELECT account_id, payload_json FROM godp_account_source "
            "WHERE account_id LIKE 'DEMO-%' AND del_flag='N' ORDER BY account_id FOR UPDATE"
        )
        for index, row in enumerate(cursor.fetchall()):
            payload = json.loads(row["payload_json"]) if row["payload_json"] else {}
            if not isinstance(payload, dict):
                payload = {}
            payload.update(demo_account_dimensions(row["account_id"], index, now, config))
            payload["updated_at"] = now.isoformat()
            cursor.execute(
                "UPDATE godp_account_source SET source_updated_at=%s, payload_json=%s, "
                "update_by='demo-account-data' WHERE account_id=%s AND del_flag='N'",
                (now.replace(tzinfo=None), json.dumps(payload, ensure_ascii=False), row["account_id"]),
            )
            updated += cursor.rowcount
        db.commit()
    print(f"Demo account organization/platform/lifecycle data updated: {updated}")


if __name__ == "__main__":
    main()
