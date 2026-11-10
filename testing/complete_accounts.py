"""Complete local test facts; never change business results or frozen algorithm inputs."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path

from .account_fixtures import complete_account
from .datasets import ROOT


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--apply',action='store_true')
    args=parser.parse_args()
    import sys
    sys.path.insert(0,str(ROOT/'python-backend'))
    from app.content_planning.bank_bridge.contracts import Account
    from app.content_planning.deployment_environment import current
    if current()['PLANNING_ENV']!='outside':
        raise ValueError('Test facts may only be completed outside')
    path=ROOT/'run/bank-source-fixture.json'
    original=path.read_bytes()
    fixture=json.loads(original)
    now=datetime.now(timezone.utc)
    changes=[]
    for entry in fixture['accounts']:
        before=entry['data']
        after=complete_account(before,now=now)
        Account.model_validate(after)
        fields=[key for key,value in after.items() if before.get(key)!=value]
        if fields:
            entry['data']=after
            entry['synthetic_fields']=sorted(set(entry.get('synthetic_fields',[]))|set(fields))
            changes.append(dict(account_id=after['account_id'],fields=fields))
    report=dict(applied=args.apply,account_count=len(fixture['accounts']),updated_accounts=len(changes),changes=changes,
                description='Missing values completed as simulated test facts; frozen snapshots are not edited')
    if args.apply and changes:
        backup=ROOT/'run/backups'/('account-facts-'+now.strftime('%Y%m%d-%H%M%S'))
        backup.mkdir(parents=True)
        (backup/'before.json').write_bytes(original)
        if path.read_bytes()!=original:
            raise ValueError('Source facts changed concurrently; completion aborted')
        temporary=path.with_suffix('.complete.tmp')
        temporary.write_text(json.dumps(fixture,ensure_ascii=False,indent=2),encoding='utf-8')
        temporary.replace(path)
        (backup/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
        report['backup']=str(backup)
    print(json.dumps({k:v for k,v in report.items() if k!='changes'},ensure_ascii=True))


if __name__=='__main__':main()
