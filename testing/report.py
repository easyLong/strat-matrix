"""Portable JSON, Markdown and self-contained HTML reports with strict baseline identity."""
from __future__ import annotations

from copy import deepcopy
from html import escape
import json
from pathlib import Path

LABELS = {"total_positions": "策划条数", "matched_positions": "正常匹配", "fallback_positions": "兜底",
          "position_shape_violations": "缺失或重复策划位置",
          "failed_positions": "未匹配", "coverage_rate": "覆盖率", "distinct_topics": "去重选题数",
          "mean_fit_score": "平均算法分", "history_violations": "历史复用违规", "city_violations": "适用范围违规",
          "role_violations": "经营作用违规", "duplicate_account_topics": "账号重复选题",
          "source_scope_violations": "输入范围违规", "persona_violations": "人设方向不符",
          "rejected_precision_used": "使用未通过精判选题"}


def baseline_snapshot(report):
    return {**{k: report[k] for k in ("schema_version", "dataset_id", "dataset_hash", "vector_space", "mode", "git_commit")},
            "engines": {name: {k: deepcopy(value[k]) for k in ("implementation_key", "policy_hash", "metrics", "positions")}
                        for name, value in report["engines"].items()}}


def compare(baseline, current):
    for key in ("schema_version", "dataset_id", "dataset_hash", "vector_space", "mode"):
        if baseline.get(key) != current.get(key):
            return {"status": "incomparable", "reason": f"{key} 不一致，禁止将不同数据或模型空间当作算法退步", "changes": [], "metric_changes": []}
    if set(baseline["engines"]) != set(current["engines"]):
        return {"status": "incomparable", "reason": "算法集合不一致", "changes": [], "metric_changes": []}
    changes, metric_changes, policy_changes = [], [], []
    for engine, value in current["engines"].items():
        old = baseline["engines"][engine]
        if old["implementation_key"] != value["implementation_key"]:
            return {"status": "incomparable", "reason": "算法实现标识不一致", "changes": [], "metric_changes": []}
        if old["policy_hash"] != value["policy_hash"]:
            policy_changes.append(engine)
        before = {(p["account_id"], p["publish_date"]): p for p in old["positions"]}
        after = {(p["account_id"], p["publish_date"]): p for p in value["positions"]}
        for key in sorted(before.keys() | after.keys()):
            left, right = before.get(key, {}), after.get(key, {})
            fields = [field for field in ("topic_id", "outcome", "content_role") if left.get(field) != right.get(field)]
            if abs((left.get("fit_score") or 0) - (right.get("fit_score") or 0)) > .000001:
                fields.append("fit_score")
            if fields:
                changes.append(dict(engine=engine, account_id=key[0], publish_date=key[1], fields=fields, before=left, after=right))
        for metric, number in value["metrics"].items():
            if abs(number - old["metrics"].get(metric, 0)) > .000001:
                metric_changes.append(dict(engine=engine, metric=metric, before=old["metrics"].get(metric), after=number))
    hard_failures = [dict(engine=e, **check) for e, v in current["engines"].items() for check in v["checks"] if not check["passed"]]
    # Selection changes require review even if aggregate coverage happens to stay the same.
    status = "failed" if hard_failures else "review" if changes or metric_changes or policy_changes else "passed"
    return dict(status=status, changes=changes, metric_changes=metric_changes, policy_changes=policy_changes, hard_failures=hard_failures)


def validate_baseline_for_recording(report):
    if not all(check["passed"] for value in report["engines"].values() for check in value["checks"]):
        raise ValueError("硬性约束未通过，禁止记录为基线")


def display(value):
    return "—" if value is None else str(value)


def write_reports(directory: Path, result):
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "algorithm.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    baseline = result["comparison"]
    lines = ["# 算法离线回归对比", "", f"- 数据集：`{result['dataset_id']}`",
             f"- 数据指纹：`{result['dataset_hash']}`", f"- 代码版本：`{result['git_commit']}`",
             f"- 结论：**{baseline['status']}**", "- 模式：固定合成向量、固定模型响应回放；真实模型调用 0，业务写入 0。",
             "- 这是代码回归基线，未经客户金标确认，不能作为真实模型效果结论。", "",
             "| 指标 | V19 |", "| --- | --- |"]
    for metric, label in LABELS.items():
        values = [result["engines"].get(e, {}).get("metrics", {}).get(metric) for e in ("v19",)]
        lines.append(f"| {label} | {display(values[0])} |")
    lines += ["", "当前仅运行 V19，与已保存的 V19 基线比较。",
              "", f"与已保存基线相比：{len(baseline['changes'])} 条结果变化。详情见同目录 `report.html` 和 `algorithm.json`。"]
    if baseline.get("reason"):
        lines += ["", baseline["reason"]]
    (directory / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    esc = lambda value: escape(display(value), quote=True)
    topics = {t["topic_id"]: t for t in result["topics"]}
    accounts = {a["account_id"]: a for a in result["accounts"]}
    metric_rows = "".join("<tr><td>" + esc(label) + "</td>" + "".join(
        "<td>" + esc(result["engines"].get(e, {}).get("metrics", {}).get(metric)) + "</td>" for e in ("v19",)) + "</tr>"
        for metric, label in LABELS.items())
    check_rows = "".join("<tr>" + "".join(f"<td>{esc(cell)}</td>" for cell in [engine.upper(), LABELS.get(c["metric"],c["metric"]), c["value"], c["maximum"], "通过" if c["passed"] else "未通过"]) + "</tr>"
                         for engine, value in result["engines"].items() for c in value["checks"])
    rows = []
    for engine, value in result["engines"].items():
        for p in sorted(value["positions"], key=lambda p: (p["account_id"], p["publish_date"])):
            topic = topics.get(p.get("topic_id"), {})
            account = accounts[p["account_id"]]
            rows.append(f'<tr data-account="{esc(p["account_id"])}" data-engine="{esc(engine)}">' + "".join(
                f'<td title="{esc(cell)}">{esc(cell)}</td>' for cell in [engine.upper(), account["account_name"], p["account_id"],
                p["publish_date"], p.get("content_role"), p.get("topic_id"), topic.get("title"), topic.get("outline"),
                topic.get("content_type"), p["outcome"], p.get("fit_score"), p.get("reason")]) + "</tr>")
    change_rows = "".join("<tr>" + "".join(f"<td>{esc(v)}</td>" for v in [
        c["engine"], c["account_id"], c["publish_date"], ", ".join(c["fields"]), c["before"].get("topic_id"), c["after"].get("topic_id")]) + "</tr>"
        for c in baseline["changes"])
    options = "".join(f'<option value="{esc(a["account_id"])}">{esc(a["account_name"])}</option>' for a in result["accounts"])
    html = f'''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>算法离线回归对比</title><style>
*{{box-sizing:border-box}}body{{margin:0;background:#f6f8fb;color:#1d2939;font:14px/1.6 system-ui,"Microsoft YaHei",sans-serif}}
main{{max-width:1500px;margin:auto;padding:28px}}h1{{font-size:24px}}h2{{font-size:17px;margin-top:0}}section{{background:white;border:1px solid #e4e8ef;border-radius:12px;padding:20px;margin:18px 0}}
.notice{{background:#fff3df;padding:14px;border-radius:8px}}.badge{{background:#eef2ff;color:#2f4be0;padding:4px 10px;border-radius:6px}}code{{word-break:break-all}}.scroll{{overflow:auto;max-height:65vh}}
table{{border-collapse:collapse;width:100%;white-space:nowrap}}td,th{{padding:10px 14px;border-bottom:1px solid #eff2f7;text-align:left;max-width:260px;overflow:hidden;text-overflow:ellipsis}}th{{background:#f6f8fb;position:sticky;top:0}}tbody tr:hover{{background:#f0f3ff}}
select{{height:36px;padding:0 12px;border:1px solid #c4ccd8;border-radius:6px;margin:0 8px 12px 0}}.meta{{color:#667085;font-size:12px}}[hidden]{{display:none}}</style>
<main><h1>算法离线回归对比 <span class="badge">{esc(baseline['status'])}</span></h1>
<div class="notice">合成数据与固定响应回放；真实模型调用 0，业务写入 0。结果用于检查代码回归，不代表真实模型效果，未经客户金标确认。</div>
<p class="meta">数据集 {esc(result['dataset_id'])}<br>数据指纹 <code>{esc(result['dataset_hash'])}</code><br>代码 {esc(result['git_commit'])}；工作区有未提交修改：{esc(result.get('git_dirty'))}<br>模型 {esc(result.get('models'))}；词表版本 {esc(result.get('taxonomy_version'))}；映射版本 {esc(result.get('mapping_version'))}</p>
<section><h2>指标</h2><p>V19 精判与分配结果，与已保存基线比较。</p><table><thead><tr><th>指标</th><th>V19</th></tr></thead><tbody>{metric_rows}</tbody></table></section>
<section><h2>与固定基线的差异：{len(baseline['changes'])} 条</h2><p>{esc(baseline.get('reason',''))}</p><div class="scroll"><table><thead><tr><th>算法</th><th>账号</th><th>投放日</th><th>变化字段</th><th>原选题</th><th>新选题</th></tr></thead><tbody>{change_rows or '<tr><td colspan="6">没有结果变化</td></tr>'}</tbody></table></div></section>
<section><h2>约束校验</h2><p>策略变化：{esc(', '.join(baseline.get('policy_changes',[])) or '无')}。使用人设映射、五路召回、模型精判与分配约束校验。</p><div class="scroll"><table><thead><tr><th>算法</th><th>指标</th><th>当前</th><th>允许上限</th><th>结论</th></tr></thead><tbody>{check_rows}</tbody></table></div></section>
<section><h2>逐账号策划结果</h2><select id="account"><option value="">全部账号</option>{options}</select>
<div class="scroll"><table><thead><tr>{''.join('<th>'+esc(x)+'</th>' for x in ['算法','账号名称','账号ID','投放日','经营作用','选题ID','标题','大纲','二级分类','结果','算法分','原因'])}</tr></thead><tbody id="results">{''.join(rows)}</tbody></table></div></section>
</main><script>function filter(){{const a=document.getElementById('account').value;document.querySelectorAll('#results tr').forEach(r=>r.hidden=(!!a&&r.dataset.account!==a));}}document.getElementById('account').addEventListener('change',filter);</script></html>'''
    (directory / "report.html").write_text(html, encoding="utf-8")
