"""Read-only delivery/host comparison. Never copies, overwrites or removes host code."""
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
from zipfile import BadZipFile, ZipFile

LAYERS = ('api', 'entity', 'client', 'services', 'server')
MODULES = {layer: 'godp-digital-marketing-' + layer for layer in LAYERS}
PACKAGE = 'com/pab/aitmp/aiis/godp/digital/marketing/'
MANIFEST = 'xiangliang-manifest.json'
MAPPERS = {'ManualMapper', 'BusinessPlanningConfigMapper', 'ConfigReleaseMapper',
           'AutoScheduleMapper', 'PlanningQueryMapper', 'SlotCompletionMapper'}


def allowed(name):
    path = PurePosixPath(name)
    if path.is_absolute() or '..' in path.parts or '\\' in name or ':' in name:
        return False
    if path.as_posix() != name:
        return False
    if path.parent == PurePosixPath('integration-templates/xiangliang'):
        return name.endswith('.java.example')
    if name == 'integration-tools/xiangliang/inspect_host_source.py':
        return True
    for layer, module in MODULES.items():
        prefix = module + '/src/main/java/' + PACKAGE
        suffixes = ('services/service/xiangliang/', 'services/mapper/xiangliang/') if layer == 'services' else (layer + '/xiangliang/',)
        for suffix in suffixes:
            if name.startswith(prefix + suffix) and name.endswith('.java'):
                return not (layer == 'server' and name.startswith(prefix + suffix + 'dev/'))
    xml_root = MODULES['services'] + '/src/main/resources/mapper/xiangliang/'
    return name in {xml_root + mapper + '.xml' for mapper in MAPPERS} | {xml_root + 'source/BankSourceMapper.xml'}


def read_package(package):
    with ZipFile(package) as archive:
        names = archive.namelist()
        if len(names) != len(set(names)) or MANIFEST not in names:
            raise ValueError('Missing manifest or duplicate archive entries')
        if sum(info.file_size for info in archive.infolist()) > 128 * 1024 * 1024:
            raise ValueError('Unexpected source package size')
        manifest = json.loads(archive.read(MANIFEST))
        if (not isinstance(manifest, dict) or manifest.get('format_version') != 1 or manifest.get('vendor') != 'xiangliang'
                or manifest.get('modules') != MODULES):
            raise ValueError('Unsupported vendor/module manifest')
        hashes = manifest.get('files')
        if not isinstance(hashes, dict) or set(hashes) != set(names) - {MANIFEST}:
            raise ValueError('Archive contents do not match manifest')
        result = {}
        for name, expected in hashes.items():
            if not allowed(name) or not isinstance(expected, str) or not re.fullmatch(r'[0-9a-f]{64}', expected):
                raise ValueError('File outside vendor boundary or invalid checksum: ' + name)
            data = archive.read(name)
            if hashlib.sha256(data).hexdigest() != expected:
                raise ValueError('Source checksum mismatch: ' + name)
            result[name] = data
    if not all(any(n.startswith(module + '/') for n in result) for module in MODULES.values()):
        raise ValueError('Incomplete five-module delivery')
    xml_root = MODULES['services'] + '/src/main/resources/mapper/xiangliang/'
    required_xml = {xml_root + mapper + '.xml' for mapper in MAPPERS} | {xml_root + 'source/BankSourceMapper.xml'}
    if not required_xml.issubset(result):
        raise ValueError('Incomplete vendor Mapper XML delivery')
    return result


def inspect(package, host_root):
    files = read_package(package)
    host = Path(host_root).resolve(strict=True)
    if not host.is_dir():
        raise ValueError('Host root must be a directory containing the five modules')
    counts = {'new': 0, 'identical': 0, 'different': 0}
    rows = []
    templates = []
    tools = []
    for name, data in sorted(files.items()):
        if name.startswith('integration-templates/'):
            templates.append(name)
            continue
        if name.startswith('integration-tools/'):
            tools.append(name)
            continue
        target = (host / name).resolve()
        if not target.is_relative_to(host):
            raise ValueError('Host vendor path resolves outside host root: ' + name)
        if target.exists() and not target.is_file():
            raise ValueError('Host file path is occupied by a directory: ' + name)
        status = 'new' if not target.exists() else ('identical' if target.read_bytes() == data else 'different')
        counts[status] += 1
        rows.append({'path': name, 'status': status})
    missing = sorted(module for module in MODULES.values() if not (host / module).is_dir())
    host_only = []
    for layer, module in MODULES.items():
        roots = [host / module / 'src/main/java' / PACKAGE / (layer + '/xiangliang')]
        if layer == 'services':
            roots = [host / module / 'src/main/java' / PACKAGE / ('services/' + branch + '/xiangliang')
                     for branch in ('service', 'mapper')]
            roots.append(host / module / 'src/main/resources/mapper/xiangliang')
        for folder in roots:
            if not folder.resolve().is_relative_to(host):
                raise ValueError('Host vendor directory resolves outside host root')
            for path in folder.rglob('*'):
                if path.is_file() and path.relative_to(host).as_posix() not in files:
                    host_only.append(path.relative_to(host).as_posix())
    return {'status': 'review_required' if counts['different'] or missing else 'ready',
            'counts': counts, 'missing_modules': missing, 'files': rows,
            'host_only_retained': sorted(host_only), 'manual_templates': templates,
            'delivery_tools': tools,
            'host_writes': 0}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--package', required=True, type=Path)
    parser.add_argument('--host-root', required=True, type=Path)
    args = parser.parse_args()
    try:
        report = inspect(args.package, args.host_root)
    except (ValueError, OSError, BadZipFile) as error:
        parser.exit(1, str(error) + '\n')
    print(json.dumps(report, ensure_ascii=False, indent=2))
    raise SystemExit(2 if report['status'] == 'review_required' else 0)
