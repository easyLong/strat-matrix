"""Build one portable code bundle without credentials, private SQL, DB data or logs."""

import argparse
from hashlib import sha256
import json
from pathlib import Path
import zipfile

from .selfcheck import schemas

ROOT = Path(__file__).resolve().parents[3]


def build_bundle(output: Path, wheel_dir: Path | None = None):
    files = {}
    for path in (ROOT / 'python-backend/app').rglob('*.py'):
        if (path.name in ('bank_sql.py', 'local_sql.py', 'site_sql_template.py', 'shared_production.py', 'shared_production_api.py')
                or path.name.startswith('run_')
                or any(part.startswith(('site_sql_private', 'site_java_private')) or part == 'legacy'
                       for part in path.relative_to(ROOT).parts)):
            continue
        files[path.relative_to(ROOT).as_posix()] = path.read_bytes()
    for name in ('.python-version', 'requirements.txt', 'schema.sql', 'pipeline_schema.sql',
                 'content_production_schema.sql', 'manual_marketing_schema.sql', 'matching_quality_schema.sql', 'manual_compute_schema.sql',
                 'algorithm_schema.sql', 'README.md', 'ONSITE.md'):
        path = ROOT / 'python-backend' / name
        files['python-backend/' + name] = path.read_bytes()
    for path in (ROOT / 'python-backend/migrations').glob('*.sql'):
        files[path.relative_to(ROOT).as_posix()] = path.read_bytes()
    files['python-backend/tools/migrate_table_audit.py'] = (ROOT / 'python-backend/tools/migrate_table_audit.py').read_bytes()
    for path in (ROOT / 'docs/integration/java-host').rglob('*'):
        if path.is_file() and (path.suffix in ('.md', '.json', '.example')):
            files[path.relative_to(ROOT).as_posix()] = path.read_bytes()
    # Public Java source is an independent subproject; no target jars or local runtime configuration.
    for name in ('pom.xml', 'README.md'):
        files['java-backend/' + name] = (ROOT / 'java-backend' / name).read_bytes()
    for path in (ROOT / 'java-backend/src').rglob('*'):
        if path.is_file() and path.suffix in ('.java', '.properties', '.sql', '.xml', '.json', '.csv'):
            files[path.relative_to(ROOT).as_posix()] = path.read_bytes()
    for path in (ROOT / 'java-backend/host-integration').rglob('*'):
        if path.is_file() and path.suffix in ('.md', '.csv', '.example', '.properties'):
            files[path.relative_to(ROOT).as_posix()] = path.read_bytes()
    files['python-backend/README.md'] = (ROOT / 'python-backend/README.md').read_bytes()
    files['frontend/README.md'] = (ROOT / 'frontend/README.md').read_bytes()
    files['docs/contracts/README.md'] = (ROOT / 'docs/contracts/README.md').read_bytes()
    files['docs/BACKGROUND_EXECUTION.md'] = (ROOT / 'docs/BACKGROUND_EXECUTION.md').read_bytes()
    files['docs/JAVA_MANUAL_MIGRATION.md'] = (ROOT / 'docs/JAVA_MANUAL_MIGRATION.md').read_bytes()
    for name in ('start.sh', 'stop.sh', 'status.sh', 'system-config.sh'):
        files[name] = (ROOT / name).read_bytes()
    files['deploy/nginx.conf.example'] = (ROOT / 'deploy/nginx.conf.example').read_bytes()
    files['docs/JAVA_INTEGRATION_BOUNDARIES.md'] = (ROOT / 'docs/JAVA_INTEGRATION_BOUNDARIES.md').read_bytes()
    files['docs/行内整合架构改造备忘_V0.1.md'] = (ROOT / 'docs/行内整合架构改造备忘_V0.1.md').read_bytes()
    files['docs/行内整合架构改造备忘_V0.2.md'] = (ROOT / 'docs/行内整合架构改造备忘_V0.2.md').read_bytes()
    frontend = ROOT / 'frontend'
    for name in ('package.json', 'package-lock.json', 'index.html', 'tsconfig.json', 'vite.config.ts'):
        files['frontend/' + name] = (frontend / name).read_bytes()
    for name in ('src', 'tooling', 'tests', 'public'):
        for path in (frontend / name).rglob('*'):
            if path.is_file():
                files[path.relative_to(ROOT).as_posix()] = path.read_bytes()
    dist = ROOT / 'frontend/dist'
    if dist.exists():
        for path in dist.rglob('*'):
            if path.is_file():
                files[path.relative_to(ROOT).as_posix()] = path.read_bytes()
    wheels = list(wheel_dir.glob('*.whl')) if wheel_dir else []
    for path in wheels:
        files['wheels/' + path.name] = path.read_bytes()
    files['contracts.json'] = json.dumps(schemas(), ensure_ascii=False, indent=2).encode('utf-8')
    files['docs/integration/java-host/contracts.json'] = files['contracts.json']
    files['mysql.env.example'] = (
        'MYSQL_HOST=\nMYSQL_PORT=3306\nMYSQL_USER=\nMYSQL_PASSWORD=\nMYSQL_DATABASE=\n').encode()
    files['install-offline.sh'] = (
        '#!/usr/bin/env sh\nset -eu\ncd "$(dirname "$0")"\n'
        'test -d wheels || { echo "Missing wheels: prepare dependencies for the bank Python/OS first."; exit 2; }\n'
        'python3 -m pip install --no-index --find-links=./wheels -r python-backend/requirements.txt\n').encode()
    files['install-offline.ps1'] = (
        "$ErrorActionPreference = 'Stop'\nSet-Location -LiteralPath $PSScriptRoot\n"
        "if (-not (Test-Path -LiteralPath 'wheels')) { throw 'Prepare wheels for the bank Python/OS first.' }\n"
        'python -m pip install --no-index --find-links=./wheels -r python-backend/requirements.txt\n'
        'if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }\n').encode()
    files['ONSITE.txt'] = (
        '驻场对接代码交接包\n\n'
        '1. Vue只访问行内Java；Java通过内网HTTP访问Python。Java主库与策划库隔离。\n'
        '2. 在 python-backend 下运行 python -m app.algorithm_schema check 和 python -m app.bank_bridge.selfcheck，先做离线DDL及契约自检。\n'
        '3. Java提供账号、选题、过审营销内容、有效营销投放及生产状态查询；SQL由行内Java实现。\n'
        '4. MySQL 连接由宿主注入，或在根目录 .env 配置；其它运行配置继续使用现有 MySQL 配置表。\n'
        '5. Python新库只运行 python -m app.init_algorithm_db --apply 创建25张算法表；已有库先检查字段，不运行旧业务初始化器。Java业务库单独发布。\n'
        '6. 配置Java资料/网关地址、双方令牌、MODEL_BASE_URL及两个模型；用 python -m app.onsite_check --target inside 校验，不会保存切换。核查后明确选择PLANNING_ENV=inside。\n'
        '7. 运行 python -m app.onsite_check --java 读取有限样本；完整资料验收另用资料契约工具。内容侧独立处理生产，状态由Java读取，Python不建生产业务表。\n'
        '8. 本包是合并宿主系统的代码与静态前端；不会自动初始化数据库或启动调度器。\n'
        '9. install-offline 脚本只使用包内 wheels。manifest 标注 not_prepared 时需按行内 Python/OS 补齐依赖。\n'
        '10. 周调度使用已批准V19策略；在 MySQL 配置 AUTO_PLANNING_POLICY_ID 和试运行账号范围 AUTO_PLANNING_ACCOUNT_IDS。\n'
        '11. java-backend为公开依赖开发壳，逐步接管业务；迁入客户Java工程时不复制本地启动壳及legacy适配器。身份权限、调度和资料SQL由宿主适配。\n'
        '12. frontend包含独立源码和dist；可并入宿主Vue工程，或部署静态产物。前端构建不依赖Python及MySQL。\n'
        '13. 查询地址及鉴权是联调草案；生产需对接行内网关、SSO和实际返回对象。本地模拟不代表真实生产接通。\n'
        '14. 当前三工程边界以docs/contracts/README.md及python-backend/ONSITE.md为准；Java宿主资料、权限及调度待接入，Maven离线依赖需另行准备，包内不含内部SDK。\n'
        'private SQL、真实账号/选题、模型密钥、数据库密码和运行日志不包含在本包内。\n'
    ).encode('utf-8')
    for name in files:
        if 'site_sql_private' in name or 'site_java_private' in name or name.endswith('/.env') or '/artifacts/' in name:
            raise ValueError('交接包包含不允许的文件')
    manifest = {
        'format_version': 6, 'source_mode': 'java_http',
        'subprojects': ['frontend', 'java-backend', 'python-backend'],
        'java_implementation': 'business_services_with_host_ports',
        'java_runtime_in_project': True,
        'java_requires_host_auth': True,
        'python_schema_entry': 'python-backend/algorithm_schema.sql',
        'python_preflight_entry': 'python -m app.onsite_check',
        'requires_site_configuration': True, 'includes_bank_schema': False,
        'includes_credentials': False, 'wheel_count': len(wheels),
        'offline_dependencies': 'provided_not_validated_for_target' if wheels else 'not_prepared',
        'files': {name: sha256(data).hexdigest() for name, data in sorted(files.items())},
    }
    files['manifest.json'] = json.dumps(manifest, ensure_ascii=False, indent=2).encode('utf-8')
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
        for name, data in sorted(files.items()):
            archive.writestr(name, data)
    return {'output': str(output), 'files': len(files), 'bytes': output.stat().st_size,
            'wheel_count': len(wheels), 'offline_dependencies': manifest['offline_dependencies']}


def main():
    parser = argparse.ArgumentParser(description='打包驻场合并代码；排除私有SQL、真实数据、密钥及日志')
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--wheel-dir', type=Path)
    args = parser.parse_args()
    if args.wheel_dir and not args.wheel_dir.is_dir():
        parser.error('--wheel-dir 必须是已准备好的离线依赖目录')
    print(json.dumps(build_bundle(args.output, args.wheel_dir)))


if __name__ == '__main__':
    main()
