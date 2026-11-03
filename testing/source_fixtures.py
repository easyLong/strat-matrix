"""Prepare the single Java-owned outside data file; no alternate data HTTP server."""
import json
import os
from pathlib import Path
import tempfile

FIXTURE_PATH = Path(__file__).resolve().parents[1] / 'run/bank-source-fixture.json'


def install(fixture, path=FIXTURE_PATH):
    """Add identified test records atomically; never replace unrelated facts or conflicting IDs."""
    original = path.read_bytes()
    current = json.loads(original)
    for key, identity in (('accounts', 'account_id'), ('topics', 'topic_id')):
        existing = {row.get('data', row)[identity]: row.get('data', row) for row in current[key]}
        for row in fixture[key]:
            if row[identity] in existing:
                if existing[row[identity]] != row:
                    raise ValueError('Test source ID already exists with different facts')
            else:
                current[key].append({'data': row, 'local_payload': {}})
                existing[row[identity]] = row
    descriptor, filename = tempfile.mkstemp(prefix='source-', suffix='.tmp', dir=path.parent)
    try:
        with os.fdopen(descriptor, 'w', encoding='utf-8') as out:
            json.dump(current, out, ensure_ascii=False, indent=2)
        if path.read_bytes() != original:
            raise ValueError('Source facts changed concurrently; installation aborted')
        os.replace(filename, path)
    finally:
        Path(filename).unlink(missing_ok=True)
