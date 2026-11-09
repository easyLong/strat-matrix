import hashlib
import importlib.util
import json
from pathlib import Path
from zipfile import ZipFile
import xml.etree.ElementTree as ET

import pytest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('host_source_export', ROOT / 'java-backend/tools/export_host_source.py')
exporter = importlib.util.module_from_spec(spec)
spec.loader.exec_module(exporter)
inspect_spec = importlib.util.spec_from_file_location('host_source_inspector', ROOT / 'java-backend/tools/inspect_host_source.py')
inspector = importlib.util.module_from_spec(inspect_spec)
inspect_spec.loader.exec_module(inspector)


def test_export_is_ready_for_existing_host_modules_without_dev_shell(tmp_path):
    target = tmp_path / 'host.zip'
    result = exporter.export(target)
    assert result['ok'] and result['mapper_xml'] == 7
    with ZipFile(target) as archive:
        manifest = json.loads(archive.read('xiangliang-manifest.json'))
        names = set(archive.namelist()) - {'xiangliang-manifest.json'}
        assert names == set(manifest['files'])
        assert set(manifest['modules'].values()) == {
            'godp-digital-marketing-' + layer for layer in ('entity', 'api', 'client', 'services', 'server')}
        assert any('/services/service/xiangliang/manual/ManualPlanningService.java' in n for n in names)
        assert any('/services/mapper/xiangliang/ManualMapper.java' in n for n in names)
        assert not any('/dev/' in n or n.endswith(('.properties', '.md', '.docx', 'pom.xml'))
                       or 'godp-planning-' in n or '/target/' in n for n in names)
        xml_names = [n for n in names if n.endswith('.xml')]
        assert all('/resources/mapper/xiangliang/' in n for n in xml_names)
        for name in names:
            data = archive.read(name)
            assert hashlib.sha256(data).hexdigest() == manifest['files'][name]
            assert b'com.pab.aitmp.aiis.godp.planning.' not in data
        for name in xml_names:
            xml = ET.fromstring(archive.read(name))
            interface = xml.attrib['namespace'].replace('.', '/') + '.java'
            assert 'godp-digital-marketing-services/src/main/java/' + interface in names
        assert manifest['source_sql'] == 'requires_host_implementation'


def test_export_refuses_overwriting_existing_delivery(tmp_path):
    target = tmp_path / 'host.zip'
    target.write_bytes(b'keep existing delivery')
    with pytest.raises(FileExistsError):
        exporter.export(target)
    assert target.read_bytes() == b'keep existing delivery'


def test_identical_sources_produce_reproducible_deliveries(tmp_path):
    first, second = tmp_path / 'first.zip', tmp_path / 'second.zip'
    assert exporter.export(first)['sha256'] == exporter.export(second)['sha256']
    assert first.read_bytes() == second.read_bytes()


def host_fixture(tmp_path):
    package = tmp_path / 'host.zip'
    exporter.export(package)
    files = inspector.read_package(package)
    host = tmp_path / 'host'
    host.mkdir()
    for name, data in files.items():
        if name.startswith(('integration-templates/', 'integration-tools/')):
            continue
        path = host / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    return package, host, files


def test_preflight_does_not_change_real_sql_or_other_vendors(tmp_path):
    package, host, files = host_fixture(tmp_path)
    sql_name = next(name for name in files if name.endswith('/source/BankSourceMapper.xml'))
    (host / sql_name).write_bytes(b'onsite custom SQL: preserve')
    missing = next(name for name in files if name.endswith('/ManualPlanningService.java'))
    (host / missing).unlink()
    custom = (host / missing).with_name('OnsitePrivateAdapter.java')
    custom.write_bytes(b'onsite adapter: preserve')
    other = host / 'godp-digital-marketing-services/src/main/java/another/vendor/SharedService.java'
    other.parent.mkdir(parents=True)
    other.write_bytes(b'other supplier: preserve')
    before = {p.relative_to(host).as_posix(): p.read_bytes() for p in host.rglob('*') if p.is_file()}
    report = inspector.inspect(package, host)
    assert report['status'] == 'review_required'
    assert report['counts']['new'] == report['counts']['different'] == 1
    assert {'path': sql_name, 'status': 'different'} in report['files']
    assert custom.relative_to(host).as_posix() in report['host_only_retained']
    assert other.relative_to(host).as_posix() not in report['host_only_retained']
    assert report['host_writes'] == 0
    assert before == {p.relative_to(host).as_posix(): p.read_bytes() for p in host.rglob('*') if p.is_file()}


def test_identical_host_is_ready_and_templates_are_not_copied(tmp_path):
    package, host, files = host_fixture(tmp_path)
    report = inspector.inspect(package, host)
    assert report['status'] == 'ready'
    assert report['counts']['new'] == report['counts']['different'] == 0
    assert report['counts']['identical'] == sum(not n.startswith(('integration-templates/', 'integration-tools/')) for n in files)
    assert report['manual_templates']
    assert report['delivery_tools']
    assert not (host / 'integration-templates').exists()
    assert not (host / 'integration-tools').exists()


def rewrite_package(source, output, change):
    with ZipFile(source) as archive:
        files = {name: archive.read(name) for name in archive.namelist()}
    change(files)
    with ZipFile(output, 'w') as archive:
        for name, data in files.items():
            archive.writestr(name, data)


def test_preflight_rejects_modified_content_even_when_zip_is_readable(tmp_path):
    source, damaged = tmp_path / 'source.zip', tmp_path / 'damaged.zip'
    exporter.export(source)
    def tamper(files):
        name = next(n for n in files if n.endswith('.java'))
        files[name] += b'\nchanged without updating manifest'
    rewrite_package(source, damaged, tamper)
    with pytest.raises(ValueError, match='checksum mismatch'):
        inspector.read_package(damaged)


@pytest.mark.parametrize('bad_path', [
    '../foreign.java',
    'godp-digital-marketing-services/src/main/java/shared/SharedService.java',
    'godp-digital-marketing-services/src/main/resources/mapper/AnotherVendor.xml',
    'godp-digital-marketing-server/src/main/java/com/pab/aitmp/aiis/godp/digital/marketing/server/xiangliang/dev/Dev.java',
])
def test_preflight_rejects_paths_outside_supplier_scope(tmp_path, bad_path):
    source, damaged = tmp_path / 'source.zip', tmp_path / 'damaged.zip'
    exporter.export(source)
    def tamper(files):
        manifest = json.loads(files['xiangliang-manifest.json'])
        files[bad_path] = b'foreign code'
        manifest['files'][bad_path] = hashlib.sha256(files[bad_path]).hexdigest()
        files['xiangliang-manifest.json'] = json.dumps(manifest).encode()
    rewrite_package(source, damaged, tamper)
    with pytest.raises(ValueError, match='outside vendor boundary'):
        inspector.read_package(damaged)
