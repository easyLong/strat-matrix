"""Verify physical modules and source dependency direction. No DB, SDK or Maven required."""
import json
import re
import xml.etree.ElementTree as ET
from pathlib import Path

from check_s0_baseline import inventory, expected_inventory

ROOT = Path(__file__).resolve().parents[1]
BASE = 'com.pab.aitmp.aiis.godp.planning'
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
            assert package.startswith(BASE + '.' + module + '.'), ('wrong layer', package)
            assert 'com.stratmatrix' not in text, ('old namespace', str(path))
            # Ignore comments; imported, fully qualified and string FQCN references all count.
            code = re.sub(r'/\*[\s\S]*?\*/|//[^\n]*', '', text)
            for dependency in re.findall(re.escape(BASE) + r'\.(\w+)\.', code):
                assert dependency == module or dependency in ancestors(module), (path.name, module, 'depends on', dependency)
        if module != 'server':
            assert not list((folder / 'src/main').rglob('application*.properties')), ('runtime config leaked', module)
    assert inventory() == expected_inventory(), 'S0 protocol/SQL drift'
    return {'ok': True, 'classes': counts, 'tables': 14, 'views': 3}


if __name__ == '__main__':
    print(json.dumps(check()))
