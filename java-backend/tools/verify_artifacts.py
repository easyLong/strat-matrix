"""Verify Java 8 project classes and separation of dev executable vs inside library artifacts."""
import json
from pathlib import Path
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[1]


def verify():
    checked = {}
    for module in ('entity', 'api', 'client', 'services'):
        path = ROOT / ('godp-planning-' + module) / 'target' / ('godp-planning-' + module + '-0.1.0-SNAPSHOT.jar')
        with ZipFile(path) as archive:
            checked[module] = verify_classes(archive)
    with ZipFile(ROOT / 'godp-planning-server/target/planning-business.jar') as archive:
        names = archive.namelist()
        assert any(n.endswith('/server/xiangliang/dev/PlanningDevelopmentApplication.class') for n in names), 'missing dev launcher'
        assert b'Main-Class: org.springframework.boot.loader.JarLauncher' in archive.read('META-INF/MANIFEST.MF')
        checked['server-dev'] = verify_classes(archive)
    with ZipFile(ROOT / 'godp-planning-server/target/inside/planning-business.jar') as archive:
        names = archive.namelist()
        assert not any('/server/xiangliang/dev/' in n or n.startswith(('BOOT-INF/', 'application')) for n in names), 'development content leaked into inside artifact'
        assert any(n.endswith('/server/xiangliang/config/PlanningHostConfiguration.class') for n in names)
        checked['server-inside'] = verify_classes(archive)
    return {'ok': True, 'java8_classes': checked, 'legacy_proxy': 'absent'}


def verify_classes(archive):
    count = 0
    for name in archive.namelist():
        if name.endswith(('LegacyPageController.class', 'PageRoutes.class')):
            raise AssertionError('deleted legacy class remains in artifact; clean module outputs first')
        assert 'com/pab/aitmp/aiis/godp/planning/' not in name, 'old package remains in artifact: ' + name
        if name.endswith('.class') and 'com/pab/aitmp/aiis/godp/digital/marketing/' in name:
            assert int.from_bytes(archive.read(name)[6:8], 'big') == 52, 'class requires newer Java: ' + name
            count += 1
    assert count > 0, 'empty project artifact'
    return count


if __name__ == '__main__':
    print(json.dumps(verify()))
