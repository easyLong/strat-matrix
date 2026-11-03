"""Complete synthetic account facts without inventing derived lifecycle or vector results."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from hashlib import sha256


def complete_account(account, *, now=None):
    original=deepcopy(account)
    account=deepcopy(account)
    now=now or datetime.now(timezone.utc)
    identity=account['account_id']
    seed=int(sha256(identity.encode()).hexdigest()[:8],16)
    persona=account.get('persona') or '生活知识分享者'
    domains=[
        (('车','自驾'),['汽车生活','自驾出行','用车经验']),
        (('亲子','育儿'),['亲子陪伴','家庭成长','教育经验']),
        (('理财','金融','财富'),['家庭预算','储蓄','金融知识','银行账户与支付']),
        (('本地','属地','城市'),['本地生活','城市出行','便民服务']),
        (('职场','工作'),['职场成长','工作经验','个人规划']),
    ]
    interests=next((values for keys,values in domains if any(key in persona for key in keys)),['生活经验','日常消费','金融常识'])
    defaults=dict(nickname=f'测试账号{seed%1000:03}',owner_um=f'TESTUM{seed%1000000:06}',
        organization='测试分行/测试二级分行',platform='小红书',account_type='认证' if seed%2 else '非认证',
        persona=persona,gender='女' if seed%2 else '男',interests=interests,
        expression_style='通俗自然，结合生活案例讲解，重视风险提示，不作收益承诺',eligible=True,followers=20)
    for key,value in defaults.items():
        if account.get(key) is None or account.get(key)=='' or account.get(key)==[]:
            account[key]=value
    posts=account.get('interactions') or []
    if not posts:
        # Keep low-follower cold-start examples below five effective posts.
        count=4 if account['followers']<50 else 8 if account['followers']<100 else 12
        posts=[dict(content_id=f'TEST-POST-{seed:08X}-{i+1:02}',account_id=identity,
                    published_at=(now-timedelta(days=3+i*5)).isoformat(),title=f'{persona}：{interests[i%len(interests)]}经验分享',
                    likes=2+seed%7+i%3,favorites=1+i%3,comments=1+i%2,updated_at=now.isoformat())
               for i in range(count)]
    for i,post in enumerate(posts):
        post.setdefault('account_id',identity)
        if not post.get('title'):post['title']=f'{persona}：生活经验分享{i+1}'
        if not post.get('updated_at'):post['updated_at']=now.isoformat()
        for field in ('likes','favorites','comments'):
            if post.get(field) is None:post[field]=0
    account['interactions']=posts
    if account != original:
        account['updated_at']=now.isoformat()
    return account
