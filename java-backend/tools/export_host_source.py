"""Export only vendor production code into the host's five existing module directories.

No POM, development launcher, runtime configuration, database data or documentation
is copied. Existing host files are never touched. Database releases remain separate.
"""
import argparse
import hashlib
import json
import re
from pathlib import Path, PurePosixPath
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]


def collect(root=ROOT):
    root = Path(root)
    layout = json.loads((root / 'contracts/vendor-layout.json').read_text(encoding='utf-8'))
    files = {}
    for name, module in layout['modules'].items():
        source = root / module['local_module'] / 'src/main/java'
        count = 0
        for path in sorted(source.rglob('*.java')):
            text = path.read_text(encoding='utf-8')
            match = re.search(r'^package ([\w.]+);', text, re.M)
            if not match:
                raise ValueError('Missing package: ' + str(path))
            package = match[1]
            if name == 'server' and (package == module['package_root'] + '.dev'
                                     or package.startswith(module['package_root'] + '.dev.')):
                continue
            mapper = name == 'services' and package == layout['mapper_package']
            if not mapper and package != module['package_root'] and not package.startswith(module['package_root'] + '.'):
                raise ValueError('Source outside vendor boundary: ' + str(path))
            relative = path.relative_to(source).as_posix()
            if relative != package.replace('.', '/') + '/' + path.name:
                raise ValueError('Package/path mismatch: ' + str(path))
            files[module['host_module'] + '/src/main/java/' + relative] = path.read_bytes()
            count += 1
        if not count:
            raise ValueError('Empty production module: ' + module['local_module'])

    services = layout['modules']['services']
    resources = root / services['local_module'] / 'src/main/resources'
    expected = [layout['mapper_resource_root'] + '/' + name + '.xml'
                for name in layout['business_mappers']] + [layout['source_mapper_resource']]
    actual = {p.relative_to(resources).as_posix() for p in resources.rglob('*.xml')}
    if actual != set(expected):
        raise ValueError('Unexpected Mapper XML layout')
    for relative in expected:
        xml = ET.parse(resources / relative).getroot()
        if xml.tag != 'mapper' or xml.attrib.get('namespace') != layout['mapper_package'] + '.' + Path(relative).stem:
            raise ValueError('Mapper namespace does not match vendor interface: ' + relative)
        files[services['host_module'] + '/src/main/resources/' + relative] = (resources / relative).read_bytes()

    # Templates are deliberately outside src: onsite implementations require real host contracts.
    for path in sorted((root / 'host-integration').glob('*.java.example')):
        files['integration-templates/xiangliang/' + path.name] = path.read_bytes()
    files['integration-tools/xiangliang/inspect_host_source.py'] = (root / 'tools/inspect_host_source.py').read_bytes()
    return layout, files


def export(output, root=ROOT):
    output = Path(output)
    layout, files = collect(root)
    manifest = {
        'format_version': 1,
        'vendor': layout['vendor'],
        'host_base_package': layout['host_base_package'],
        'modules': {name: module['host_module'] for name, module in layout['modules'].items()},
        'host_beans': layout['host_beans'],
        'source_sql': 'requires_host_implementation',
        'database_release': 'publish_separately',
        'files': {name: hashlib.sha256(data).hexdigest() for name, data in sorted(files.items())},
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    for name in files:
        path = PurePosixPath(name)
        if path.is_absolute() or '..' in path.parts:
            raise ValueError('Unsafe archive path')

    def write(archive, name, data):
        # Identical source yields identical archives: avoid timestamp-only delivery differences.
        info = ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
        info.create_system = 3
        info.external_attr = 0o100644 << 16
        info.compress_type = ZIP_DEFLATED
        archive.writestr(info, data)

    # Refuse overwriting an existing review/delivery package.
    with ZipFile(output, 'x', compression=ZIP_DEFLATED) as archive:
        for name, data in sorted(files.items()):
            write(archive, name, data)
        write(archive, 'xiangliang-manifest.json', (json.dumps(manifest, ensure_ascii=False, indent=2) + '\n').encode('utf-8'))
    return {'ok': True, 'output': str(output.resolve()), 'files': len(files),
            'java': sum(n.endswith('.java') for n in files),
            'mapper_xml': sum(n.endswith('.xml') for n in files),
            'sha256': hashlib.sha256(output.read_bytes()).hexdigest()}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    print(json.dumps(export(args.output), ensure_ascii=False))
