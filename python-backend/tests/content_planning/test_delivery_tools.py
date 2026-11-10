"""Portable artifacts and offline inventory must work without DB/model access."""
import json
from hashlib import sha256
from pathlib import Path
import subprocess
import sys
from zipfile import ZipFile
from tools.content_planning.export_module import export
from tools.content_planning.inspect_dependencies import inventory


def test_delivery_manifest_hashes_match_and_private_state_is_excluded(tmp_path):
    result=export(tmp_path/'module.zip')
    with ZipFile(result['archive']) as archive:
        manifest=json.loads(archive.read('module-manifest.json'))
        assert manifest['version']=='0.3.0'
        assert 'app/main.py' not in archive.namelist()
        assert 'app/standalone_config.py' not in archive.namelist()
        for row in manifest['files']:
            data=archive.read(row['path'])
            assert len(data)==row['size'] and sha256(data).hexdigest()==row['sha256']
            assert not any(part in ('.env','.venv','__pycache__','run') for part in Path(row['path']).parts)
        assert manifest['database_entry'] in archive.namelist()
        archive.extractall(tmp_path/'host')
    root=tmp_path/'host'
    import os
    # Exported SQL works from a foreign cwd, without the original repository.
    command=[sys.executable,'-m','tools.content_planning.schema','check','--resource-directory',
             str(root/'database/content_planning')]
    proc=subprocess.run(command,cwd=tmp_path,env={**os.environ,'PYTHONPATH':str(root)},capture_output=True,text=True,timeout=30)
    assert proc.returncode==0,proc.stderr
    assert json.loads(proc.stdout)['database_writes']==0


def test_inventory_keeps_algorithm_ownership_separate_from_compatibility_dependencies():
    result=inventory();rows={r['table']:r for r in result['sql_literal_references']}
    assert result['algorithm_owned_table_count']==25 and result['database_connections']==0
    assert rows['godp_planning_batch']['ownership']=='compatibility_or_business'
    assert 'ai_preparation.py' in rows['godp_planning_batch']['files']
    assert 'ordinary_scheduler.py' in rows['godp_auto_plan_run']['files']
