"""Offline schema commands; all database writes require a separate explicit action."""
from app.content_planning.algorithm_schema import main

if __name__ == '__main__':
    raise SystemExit(main())
