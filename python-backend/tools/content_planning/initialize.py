"""Explicit algorithm-only DDL command. Prefer DBA-reviewed SQL in bank environments."""
import argparse
import asyncio
from dataclasses import replace
import json
from pathlib import Path


def main(argv=None):
    parser = argparse.ArgumentParser(description='Explicit algorithm schema initialization; never run on API startup')
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--resource-directory', type=Path, required=True)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--config-file', type=Path, help='Host PLANNING_* JSON file; never copied into delivery')
    group.add_argument('--standalone', action='store_true', help='Explicitly load the current development .env')
    args = parser.parse_args(argv)
    if not args.apply:
        parser.error('Database writes require --apply; export/check commands are offline')
    from app.content_planning.config import PlanningConfig
    from app.content_planning.runtime import PlanningRuntime
    from app.content_planning.init_algorithm_db import initialize
    if args.standalone:
        from app.standalone_config import load_config
        config = load_config()
    else:
        config = PlanningConfig.from_mapping(json.loads(args.config_file.read_text(encoding='utf-8-sig')))
    config = replace(config, resource_directory=args.resource_directory.resolve())
    runtime = PlanningRuntime(config)
    try:
        with runtime.bind():
            result = initialize()
    except Exception:
        result = {'status': 'not_ready', 'reason': 'Initialization failed; DDL may have partially committed. Review permissions and schema.'}
    finally:
        asyncio.run(runtime.close())
    print(json.dumps(result, ensure_ascii=True))
    return 0 if result['status'] == 'passed' else 2


if __name__ == '__main__':
    raise SystemExit(main())
