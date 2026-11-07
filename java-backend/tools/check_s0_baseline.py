"""Freeze/check S0's HTTP annotations, input fields and business SQL without DB/network I/O."""
import argparse
import hashlib
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASELINE = ROOT / 'contracts/s0-baseline.json'
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
    # The old location allows capturing before the first physical move.
    modules = list(ROOT.glob('godp-planning-*/src/main')) or [ROOT / 'src/main']
    sources = {p.stem: p.read_text(encoding='utf-8') for m in modules for p in m.rglob('*.java')}
    sql = next(m / 'resources/db' for m in modules if (m / 'resources/db/manual-business.sql').exists())
    files = sorted(p for p in sql.rglob('*.sql') if 'release' not in p.relative_to(sql).parts)
    tables, views = set(), set()
    for path in sql.glob('*.sql'):
        content = path.read_text(encoding='utf-8')
        tables.update(re.findall(r'CREATE TABLE IF NOT EXISTS (\w+)', content, re.I))
        views.update(re.findall(r'CREATE (?:OR REPLACE )?VIEW (\w+)', content, re.I))
    return {
        'description': 'S1 preserves HTTP mapping/status annotations, public input fields and SQL bytes; full behavior is covered by MVC/H2/browser tests.',
        'http_annotations': {name: annotations(sources[name]) for name in CONTROLLERS},
        'input_fields': {name: re.findall(r'^  public (?!class\b|static\b)([^\n{]+;)$', sources[name], re.M) for name in INPUTS},
        'tables': sorted(tables), 'views': sorted(views),
        'sql_sha256': {p.relative_to(sql).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in files},
    }


def expected_inventory():
    expected = json.loads(BASELINE.read_text(encoding='utf-8'))
    additions = ROOT / 'contracts/s4-post-additions.json'
    if additions.exists():
        for controller, routes in json.loads(additions.read_text(encoding='utf-8')).items():
            if controller not in expected['http_annotations'] or any(not route.startswith('@PostMapping') for route in routes):
                raise ValueError('Only explicitly reviewed additive POST mappings are allowed in S4')
            expected['http_annotations'][controller].extend(routes)
    return expected


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--capture', action='store_true', help='Create only; never overwrite an existing approved baseline')
    args = parser.parse_args()
    actual = inventory()
    if args.capture:
        BASELINE.parent.mkdir(parents=True, exist_ok=True)
        with BASELINE.open('x', encoding='utf-8', newline='\n') as stream:
            json.dump(actual, stream, ensure_ascii=False, indent=2)
            stream.write('\n')
    expected = expected_inventory()
    if actual != expected:
        changed = [key for key in expected.keys() | actual.keys() if expected.get(key) != actual.get(key)]
        raise SystemExit('S0 baseline changed; review deliberately before changing: ' + ', '.join(changed))
    print(json.dumps({'ok': True, 'controllers': len(CONTROLLERS), 'tables': len(actual['tables']),
                      'views': len(actual['views']), 'sql_files': len(actual['sql_sha256'])}))


if __name__ == '__main__':
    main()
