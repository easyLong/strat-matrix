"""Fill missing UM identifiers on existing DEMO-* account source payloads."""

import json

from .db import connection
from .demo_um import demo_um_no


def main() -> None:
    updated = 0
    with connection() as db, db.cursor() as cursor:
        cursor.execute(
            "SELECT account_id, payload_json FROM godp_account_source "
            "WHERE account_id LIKE 'DEMO-%' AND del_flag='N' ORDER BY account_id FOR UPDATE"
        )
        rows = cursor.fetchall()
        for row in rows:
            payload = json.loads(row["payload_json"]) if row["payload_json"] else {}
            if not isinstance(payload, dict) or payload.get("um_no"):
                continue
            payload["um_no"] = demo_um_no(row["account_id"])
            cursor.execute(
                "UPDATE godp_account_source SET payload_json=%s, update_by='demo-um-seed' "
                "WHERE account_id=%s AND del_flag='N'",
                (json.dumps(payload, ensure_ascii=False), row["account_id"]),
            )
            updated += cursor.rowcount
        db.commit()
    print(f"Demo account UM numbers added: {updated}")


if __name__ == "__main__":
    main()
