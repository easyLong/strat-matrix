"""Create and seed the planner mapping table only; never overwrite reviewed rules."""
import json
from pathlib import Path

from .account_mapping_seed import build_seed_rules
from .db import connection
from .init_planner_db import statements
from .services.account_mapping import load_taxonomy
from .services.errors import ApplicationError


def seed_rules(cursor):
    try:
        version, taxonomy = load_taxonomy(cursor)
    except ApplicationError as exc:
        if exc.status_code == 409:
            return {'inserted': 0, 'existing': 0, 'reason': 'taxonomy_not_initialized'}
        raise
    rules, unresolved = build_seed_rules(taxonomy, version)
    report = {'mapping_version': 1, 'taxonomy_version': version,
              'inserted': 0, 'existing': 0, 'unresolved': unresolved}
    for rule in rules:
        payload = rule.model_dump(exclude={'id'})
        columns = list(payload)
        cursor.execute('INSERT INTO godp_account_mapping_rule (' + ','.join(columns) + ') VALUES ('
                       + ','.join(['%s'] * len(columns)) + ') ON DUPLICATE KEY UPDATE id=id',
                       [payload[key] for key in columns])
        report['inserted' if cursor.rowcount == 1 else 'existing'] += 1
    return report


def main():
    source = (Path(__file__).resolve().parents[1] / 'schema.sql').read_text(encoding='utf-8')
    ddl = next(s for s in statements(source) if 'EXISTS godp_account_mapping_rule (' in s)
    with connection() as db, db.cursor() as cursor:
        cursor.execute(ddl)
        report = seed_rules(cursor)
        db.commit()
    print(json.dumps(report, ensure_ascii=False))


if __name__ == '__main__':
    main()
