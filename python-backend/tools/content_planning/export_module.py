"""Export the portable module and reviewed resources without local credentials."""
import argparse
from hashlib import sha256
import json
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED, ZipInfo


def export(destination):
    backend = Path(__file__).resolve().parents[2]
    roots = ('app/content_planning', 'database/content_planning', 'tools/content_planning',
             'tests/content_planning', 'examples')
    files = []
    for name in roots:
        for path in (backend / name).rglob('*'):
            relative = path.relative_to(backend)
            if not path.is_file() or any(part.startswith(('.', '__pycache__')) for part in relative.parts):
                continue
            if path.suffix not in ('.py', '.json', '.sql', '.md', '.txt') and path.name != 'VERSION':
                continue
            if any('private' in part.lower() for part in relative.parts):
                continue
            files.append(path)
    files += [backend / name for name in ('requirements.txt', 'requirements-dev.txt', 'INTEGRATION.md',
                                         'VALIDATION.md', 'validation-results.json')]
    entries = [(p.relative_to(backend).as_posix(), p.read_bytes()) for p in sorted(set(files))]
    manifest = {
        'module': 'content_planning',
        'version': (backend / 'app/content_planning/VERSION').read_text().strip(),
        'algorithm_contract': 'V19; compare frozen-input replay against the approved baseline',
        'files': [{'path': name, 'size': len(data), 'sha256': sha256(data).hexdigest()} for name, data in entries],
        'excluded': ['app/main.py', 'app/standalone_config.py', '.env', 'local credentials',
                     'private adapters', 'node_modules', '.venv', 'logs', 'run', 'Java/frontend projects'],
        'database_entry': 'database/content_planning/algorithm_schema.sql',
        'requires_dependency_review': True,
    }
    destination = Path(destination).resolve()
    if destination.exists():
        raise ValueError('Refusing to overwrite an existing delivery archive')
    destination.parent.mkdir(parents=True, exist_ok=True)
    entries.append(('module-manifest.json', (json.dumps(manifest, ensure_ascii=False, indent=2) + '\n').encode('utf-8')))
    with ZipFile(destination, 'x', compression=ZIP_DEFLATED, compresslevel=9) as archive:
        for name, data in entries:
            info = ZipInfo(name, date_time=(2026, 11, 10, 0, 0, 0))
            info.compress_type = ZIP_DEFLATED
            archive.writestr(info, data)
    digest = sha256(destination.read_bytes()).hexdigest()
    destination.with_suffix(destination.suffix + '.sha256').write_text(digest + '  ' + destination.name + '\n', encoding='ascii')
    return {'archive': str(destination), 'sha256': digest, 'file_count': len(entries)}


def main(argv=None):
    parser = argparse.ArgumentParser(description='Build a credential-free content_planning host integration package')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(argv)
    print(json.dumps(export(args.output)))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
