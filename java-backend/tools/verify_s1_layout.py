"""Verify physical modules and source dependency direction. No DB, SDK or Maven required."""
import json
import re
import xml.etree.ElementTree as ET
from pathlib import Path

from check_contract import inventory, expected_inventory

ROOT = Path(__file__).resolve().parents[1]
LAYOUT = json.loads((ROOT / 'contracts/vendor-layout.json').read_text(encoding='utf-8'))
BASE = LAYOUT['host_base_package']
NS = {'m': 'http://maven.apache.org/POM/4.0.0'}
DIRECT = {'entity': set(), 'api': {'entity'}, 'client': {'api'},
          'services': {'api', 'client'}, 'server': {'services', 'client'}}


def ancestors(module):
    result = set(DIRECT[module])
    for dependency in DIRECT[module]:
        result.update(ancestors(dependency))
    return result


def check():
    pom = ET.parse(ROOT / 'pom.xml').getroot()
    assert pom.findtext('m:packaging', namespaces=NS) == 'pom', 'root must be an aggregator'
    assert set(m.text for m in pom.findall('m:modules/m:module', NS)) == {'godp-planning-' + m for m in DIRECT}
    assert not list((ROOT / 'src').rglob('*.java')), 'unmigrated Java source'
    counts = {}
    for module in DIRECT:
        folder = ROOT / ('godp-planning-' + module)
        tree = ET.parse(folder / 'pom.xml').getroot()
        actual = {d.findtext('m:artifactId', namespaces=NS).removeprefix('godp-planning-')
                  for d in tree.findall('m:dependencies/m:dependency', NS)
                  if d.findtext('m:groupId', namespaces=NS) == 'com.pab.aitmp.aiis'}
        assert actual == DIRECT[module], (module, 'module dependencies differ', actual)
        files = list((folder / 'src/main/java').rglob('*.java'))
        counts[module] = len(files)
        assert files, ('empty module', module)
        for path in files:
            text = path.read_text(encoding='utf-8')
            package = re.search(r'^package ([\w.]+);', text, re.M)[1]
            expected = folder / 'src/main/java' / package.replace('.', '/') / path.name
            assert path == expected, ('wrong physical package', str(path))
            prefix = LAYOUT['modules'][module]['package_root']
            is_mapper = module == 'services' and path.stem in LAYOUT['business_mappers'] + [LAYOUT['source_mapper']]
            expected_package = LAYOUT['mapper_package'] if is_mapper else prefix
            assert package == expected_package or package.startswith(expected_package + '.'), ('wrong layer/vendor', package)
            assert 'com.stratmatrix' not in text and 'com.pab.aitmp.aiis.godp.planning' not in text, ('old namespace', str(path))
            # Ignore comments; imported, fully qualified and string FQCN references all count.
            code = re.sub(r'/\*[\s\S]*?\*/|//[^\n]*', '', text)
            for dependency in re.findall(re.escape(BASE) + r'\.(\w+)\.', code):
                assert dependency == module or dependency in ancestors(module), (path.name, module, 'depends on', dependency)
        if module != 'server':
            assert not list((folder / 'src/main').rglob('application*.properties')), ('runtime config leaked', module)
    resources = ROOT / 'godp-planning-services/src/main/resources'
    mapper_paths = [resources / LAYOUT['mapper_resource_root'] / (name + '.xml') for name in LAYOUT['business_mappers']]
    mapper_paths.append(resources / LAYOUT['source_mapper_resource'])
    assert len(list(resources.rglob('*.xml'))) == len(mapper_paths) == 7, 'unexpected mapper resource outside vendor directory'
    for path in mapper_paths:
        assert path.exists(), ('missing vendor XML', str(path))
        root = ET.parse(path).getroot()
        assert root.tag == 'mapper' and root.attrib['namespace'] == LAYOUT['mapper_package'] + '.' + path.stem, ('wrong Mapper namespace', str(path))
        assert 'com.pab.aitmp.aiis.godp.planning' not in path.read_text(encoding='utf-8'), ('old XML type reference', str(path))
    assert inventory() == expected_inventory(), 'API/SQL contract drift'
    assert inventory()['views'] == [], 'bank runtime must not depend on database views'
    return {'ok': True, 'vendor': LAYOUT['vendor'], 'classes': counts, 'mapper_xml': len(mapper_paths), 'tables': 14, 'views': 0}


if __name__ == '__main__':
    print(json.dumps(check()))
