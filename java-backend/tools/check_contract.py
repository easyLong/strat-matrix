"""Check the final POST contract, input fields and business SQL without DB/network I/O."""
import argparse
import hashlib
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASELINE = ROOT / 'contracts/api-contract.json'
CONTROLLERS = ('ManualPlanningController', 'BusinessPlanningConfigController',
               'ConfigReleaseController', 'TagTaxonomyController',
               'SourceFactsController', 'PlanningHealthController')
INPUTS = ('ManualPreviewRequest', 'MarketingTaskRequest', 'BusinessPlanningConfig')


def annotations(text):
    result = []
    for match in re.finditer(r'@(GetMapping|PostMapping|PutMapping|DeleteMapping|PatchMapping|RequestMapping|ResponseStatus)\b', text):
        i = match.end()
        while i < len(text) and text[i].isspace():
            i += 1
        end = i
        if i < len(text) and text[i] == '(':
            depth, quoted, escaped = 0, False, False
            for end in range(i, len(text)):
                char = text[end]
                if quoted:
                    if escaped:
                        escaped = False
                    elif char == '\\':
                        escaped = True
                    elif char == '"':
                        quoted = False
                elif char == '"':
                    quoted = True
                elif char == '(':
                    depth += 1
                elif char == ')':
                    depth -= 1
                    if depth == 0:
                        end += 1
                        break
        result.append(re.sub(r'\s+', ' ', text[match.start():end]).strip())
    return result


def inventory():
    modules = list(ROOT.glob('godp-planning-*/src/main'))
    sources = {p.stem: p.read_text(encoding='utf-8') for m in modules for p in m.rglob('*.java')}
    sql = next(m / 'resources/db' for m in modules if (m / 'resources/db/manual-business.sql').exists())
    files = sorted(p for p in sql.rglob('*.sql') if 'release' not in p.relative_to(sql).parts)
    tables, views = set(), set()
    for path in sql.glob('*.sql'):
        content = path.read_text(encoding='utf-8')
        tables.update(re.findall(r'CREATE TABLE IF NOT EXISTS (\w+)', content, re.I))
        views.update(re.findall(r'CREATE (?:OR REPLACE )?VIEW (\w+)', content, re.I))
    return {
        'description': 'Final POST-only business contract; GET is reserved for health. Input fields and SQL bytes are independently frozen.',
        'http_annotations': {name: annotations(sources[name]) for name in CONTROLLERS},
        'input_fields': {name: re.findall(r'^  public (?!class\b|static\b)([^\n{]+;)$', sources[name], re.M) for name in INPUTS},
        'tables': sorted(tables), 'views': sorted(views),
        'sql_sha256': {p.relative_to(sql).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in files},
    }


def expected_inventory():
    expected = json.loads(BASELINE.read_text(encoding='utf-8'))
    return expected


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--capture', action='store_true', help='Create only; never overwrite an existing approved baseline')
    args = parser.parse_args()
    actual = inventory()
    for name, routes in actual['http_annotations'].items():
        for route in routes:
            if route.startswith('@GetMapping'):
                assert name == 'PlanningHealthController' and route == '@GetMapping("/health")', (name, route)
            assert not route.startswith(('@PutMapping', '@PatchMapping', '@DeleteMapping')), (name, route)
    if args.capture:
        BASELINE.parent.mkdir(parents=True, exist_ok=True)
        with BASELINE.open('x', encoding='utf-8', newline='\n') as stream:
            json.dump(actual, stream, ensure_ascii=False, indent=2)
            stream.write('\n')
    expected = expected_inventory()
    if actual != expected:
        changed = [key for key in expected.keys() | actual.keys() if expected.get(key) != actual.get(key)]
        raise SystemExit('API/SQL contract changed; review deliberately before changing: ' + ', '.join(changed))
    print(json.dumps({'ok': True, 'controllers': len(CONTROLLERS), 'tables': len(actual['tables']),
                      'views': len(actual['views']), 'sql_files': len(actual['sql_sha256'])}))


if __name__ == '__main__':
    main()
