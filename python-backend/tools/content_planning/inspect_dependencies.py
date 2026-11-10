"""Offline source inventory, not a substitute for execution-path acceptance."""
import argparse
import ast
import json
from pathlib import Path
import re
from app.content_planning.algorithm_schema import REQUIRED_TABLES
from app.content_planning import resources


def inventory():
    package = Path(resources.__file__).resolve().parent
    references = {}
    for path in sorted(package.rglob('*.py')):
        # Only string constants with SQL table positions; includes tools/legacy
        # deliberately so compatibility dependencies cannot be silently hidden.
        for node in ast.walk(ast.parse(path.read_text(encoding='utf-8-sig'))):
            if not isinstance(node, ast.Constant) or not isinstance(node.value, str):
                continue
            for table in re.findall(r'\b(?:FROM|JOIN|INTO|UPDATE|TABLE(?:\s+IF\s+NOT\s+EXISTS)?)\s+`?(godp_\w+)', node.value, re.I):
                references.setdefault(table, set()).add(path.relative_to(package).as_posix())
    return {
        'status': 'inventory_only', 'database_connections': 0,
        'algorithm_owned_table_count': len(REQUIRED_TABLES),
        'algorithm_owned_tables': sorted(REQUIRED_TABLES),
        'sql_literal_references': [
            {'table': table, 'ownership': 'algorithm' if table in REQUIRED_TABLES else 'compatibility_or_business',
             'files': sorted(files)} for table, files in sorted(references.items())],
        'limitations': ['Static literal scan includes legacy/tool branches and may miss dynamically assembled SQL.',
                       '25 algorithm-owned tables are not proof that every compatibility execution path is satisfied.',
                       'Read README.md for branch gates, Java contracts, deployment and rollback rules.'],
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description='Offline SQL dependency inventory; never connects to MySQL')
    parser.add_argument('--output', type=Path)
    args = parser.parse_args(argv)
    result = json.dumps(inventory(), ensure_ascii=False, indent=2) + '\n'
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(result, encoding='utf-8')
    else:
        print(result)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
