"""One entry for isolated regression, fixed algorithm replay and portable reports."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

from .datasets import ROOT, load
from .report import baseline_snapshot, compare, validate_baseline_for_recording, write_reports


def executable(name, override=None):
    if override:
        found = shutil.which(override) or (override if Path(override).is_file() else None)
    else:
        found = shutil.which(name)
        if not found and name == "mvn":
            candidates = sorted((ROOT / ".tmp-tools" / "maven").glob("*/bin/mvn.cmd" if os.name == "nt" else "*/bin/mvn"))
            found = str(candidates[-1]) if candidates else None
    if not found:
        raise ValueError(f"缺少工具 {name}，本轮不能标记通过")
    return found


def command_step(name, argv, cwd, output, environment, timeout):
    started = time.monotonic()
    log = output / f"{name}.log"
    try:
        with log.open("w", encoding="utf-8") as stream:
            process = subprocess.run(argv, cwd=cwd, env=environment, stdout=stream, stderr=subprocess.STDOUT,
                                     timeout=timeout, check=False)
        code, status = process.returncode, "passed" if process.returncode == 0 else "failed"
    except subprocess.TimeoutExpired:
        code, status = 124, "timeout"
    except OSError as exc:
        code, status = 127, "unavailable"
        log.write_text(f"无法启动测试命令：{type(exc).__name__}\n", encoding="utf-8")
    return dict(name=name, status=status, exit_code=code, duration_seconds=round(time.monotonic() - started, 3), log=log.name)


def main(argv=None):
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="固定合成数据、统一回归和离线算法对比；默认不访问模型和现有数据库")
    parser.add_argument("--suite", choices=["all", "algorithm", "python", "java", "frontend"], default="all")
    parser.add_argument("--dataset", choices=["small", "scale"], default="small")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--baseline", type=Path, help="可用上次algorithm.json或精简基线；数据指纹必须一致")
    parser.add_argument("--candidate-policy", type=Path, help="JSON对象，按v19指定待比较策略；不写入系统策略库")
    parser.add_argument("--record-baseline", action="store_true", help="显式记录/更新固定基线，常规回归绝不自动更新")
    parser.add_argument("--maven", help="Maven可执行文件路径")
    parser.add_argument("--java-home", type=Path, help="与宿主兼容的本地JDK目录")
    parser.add_argument("--allow-dependency-network", action="store_true", help="只允许Maven解析依赖；模型和算法回归仍离线")
    parser.add_argument("--timeout", type=int, default=600, help="每条测试命令的秒数上限")
    args = parser.parse_args(argv)
    if args.timeout < 1:
        parser.error("timeout必须为正数")
    if args.record_baseline and args.suite != "algorithm":
        parser.error("记录基线须显式使用 --suite algorithm")
    if args.baseline and args.record_baseline:
        parser.error("指定对比文件时不能同时覆盖默认基线")
    output = (args.output or ROOT / "run" / "regression" / datetime.now().strftime("%Y%m%d-%H%M%S-%f")).resolve()
    if output.exists() and any(output.iterdir()):
        parser.error("输出目录已有文件，请换一个目录以保留历史证据")
    output.mkdir(parents=True, exist_ok=True)
    environment = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONUTF8="1", GIT_TERMINAL_PROMPT="0")
    environment["PYTHONPATH"] = os.pathsep.join([str(ROOT), str(ROOT / "python-backend"), environment.get("PYTHONPATH", "")])
    java_home = args.java_home or (Path(environment["JAVA_HOME"]) if environment.get("JAVA_HOME") else None)
    if java_home is None:
        local = sorted((ROOT / ".tmp-tools" / "jdk").glob("*/bin/java.exe" if os.name == "nt" else "*/bin/java"))
        if local:
            java_home = local[-1].parent.parent
    if java_home:
        environment["JAVA_HOME"] = str(java_home.resolve())
    steps = []
    suites = {"algorithm", "python", "java", "frontend"} if args.suite == "all" else {args.suite}
    result = None
    if "algorithm" in suites:
        print("[algorithm] 固定数据与现有 V19 代码回放", flush=True)
        started = time.monotonic()
        try:
            sys.path.insert(0, str(ROOT / "python-backend"))
            from .evaluate import evaluate
            dataset = load(args.dataset)
            candidate = json.loads(args.candidate_policy.read_text(encoding="utf-8")) if args.candidate_policy else None
            if candidate is not None and (not isinstance(candidate, dict) or not candidate or set(candidate) - {"v19"}):
                raise ValueError("候选策略须为包含v19键的非空对象")
            result = evaluate(dataset, candidate)
            baseline_path = args.baseline or ROOT / "testing" / "baselines" / f"{args.dataset}-v19.json"
            if args.record_baseline:
                validate_baseline_for_recording(result)
                baseline_path.parent.mkdir(parents=True, exist_ok=True)
                baseline_path.write_text(json.dumps(baseline_snapshot(result), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            if baseline_path.exists():
                result["comparison"] = compare(json.loads(baseline_path.read_text(encoding="utf-8")), result)
            else:
                result["comparison"] = dict(status="unbaselined", reason="缺少固定基线，需检查结果后显式记录", changes=[], metric_changes=[])
            write_reports(output, result)
            steps.append(dict(name="algorithm", status=result["comparison"]["status"],
                              duration_seconds=round(time.monotonic() - started, 3), log="report.html"))
        except Exception as exc:
            # No trace/config dump: tools may eventually be run alongside real local credentials.
            (output / "algorithm-error.log").write_text(f"{type(exc).__name__}: {str(exc)[:500]}\n", encoding="utf-8")
            steps.append(dict(name="algorithm", status="failed", error_type=type(exc).__name__, log="algorithm-error.log"))
    jobs = []
    if "python" in suites:
        jobs += [("python", [sys.executable, "-m", "pytest", "-p", "testing.pytest_plugin", "-q"], ROOT / "python-backend"),
                 ("harness", [sys.executable, "-m", "pytest", "-p", "testing.pytest_plugin", "-q", "testing/tests"], ROOT)]
    if "java" in suites:
        try:
            maven = executable("mvn", args.maven)
            jobs.append(("java", [maven, *([] if args.allow_dependency_network else ["-o"]), "-q",
                                 "-Dplanning.real-acceptance-properties=", "-Dplanning.full-chain-properties=",
                                 "-Dplanning.content-acceptance-properties=", "-Dmanual.live=false", "test"], ROOT / "java-backend"))
        except ValueError as exc:
            steps.append(dict(name="java", status="unavailable", reason=str(exc)))
    if "frontend" in suites:
        try:
            npm = executable("npm.cmd" if os.name == "nt" else "npm")
            jobs += [("frontend-tests", [npm, "test"], ROOT / "frontend"),
                     ("frontend-build", [npm, "run", "build"], ROOT / "frontend")]
        except ValueError as exc:
            steps.append(dict(name="frontend", status="unavailable", reason=str(exc)))
    for name, command, cwd in jobs:
        print(f"[{name}] 开始", flush=True)
        step = command_step(name, command, cwd, output, environment, args.timeout)
        steps.append(step)
        print(f"[{name}] {step['status']}", flush=True)
    ok = all(s["status"] == "passed" for s in steps)
    summary = dict(schema_version=1, status="passed" if ok else "not_passed", suite=args.suite, dataset=args.dataset,
                   created_at=datetime.now(timezone.utc).isoformat(), steps=steps,
                   real_model_evaluation="not_run", production_writes=0,
                   note="不包含行内真实适配、真实模型质量或生产环境验收")
    (output / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"结果：{summary['status']}\n报告目录：{output}", flush=True)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
