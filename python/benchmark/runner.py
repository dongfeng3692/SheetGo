"""SpreadsheetBench 跑分脚本 — 通过 Exceler Agent 入口测试

流程:
  1. 下载/解压 SpreadsheetBench 数据集
  2. 对每个任务:
     - 复制 input.xlsx 到工作目录
     - 构造用户消息（指令 + 文件路径）
     - 调用 AgentEngine.chat()（完整 function calling 流程）
     - 复制工作文件为 output.xlsx
  3. 用 evaluator 逐格比对 output vs answer
  4. 输出报告（通过率 + 工具调用次数 + 错误次数 + token 等）

用法:
  # OpenAI / 兼容 API（默认）
  python -m python.benchmark.runner --model gpt-4o --api-key sk-xxx --max-tasks 10

  # Anthropic Claude（直接 SDK）
  python -m python.benchmark.runner --provider anthropic --model claude-sonnet-4-20250514 --api-key sk-ant-xxx
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import shutil
import sys
import tarfile
import time
import urllib.request
from dataclasses import dataclass, field
from typing import Any

# 项目根目录
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from agent import (
    AgentEngine,
    ConversationState,
    EvDone,
    EvError,
    EvTextDelta,
    EvTextEnd,
    EvTextStart,
    EvToolCallEnd,
    EvToolCallStart,
    HookManager,
    LLMConfig,
    LLMProvider,
    PromptBuilder,
    ToolRegistry,
)
from tools import create_default_tools
from config import benchmark as bench_cfg

from .evaluator import evaluate_dataset, print_report, save_report

# ============================================================================
# 常量
# ============================================================================

_DATASETS = bench_cfg.datasets
_DATA_ROOT = bench_cfg.data_root if hasattr(bench_cfg, 'data_root') else os.path.normpath(os.path.join(
    os.path.dirname(__file__), "..", "..", "data", "spreadsheetbench"
))

_USER_PROMPT_TEMPLATE = """\
请完成以下 Excel 任务:

{instruction}

文件路径: {file_path}
"""


# ============================================================================
# 数据集下载
# ============================================================================


def _download_file(url: str, dest: str) -> None:
    print(f"下载: {url}")
    tmp = dest + ".tmp"
    try:
        urllib.request.urlretrieve(url, tmp)
        shutil.move(tmp, dest)
    except Exception:
        if os.path.exists(tmp):
            os.remove(tmp)
        raise


def ensure_dataset(dataset_name: str) -> str:
    """确保数据集已下载解压，返回数据集根目录"""
    if dataset_name not in _DATASETS:
        if os.path.isdir(dataset_name):
            return dataset_name
        raise ValueError(
            f"未知数据集: {dataset_name}\n可用: {', '.join(_DATASETS.keys())} 或本地路径"
        )

    info = _DATASETS[dataset_name]
    os.makedirs(_DATA_ROOT, exist_ok=True)

    extracted_dir = os.path.join(_DATA_ROOT, dataset_name)
    if os.path.isdir(extracted_dir) and os.path.exists(os.path.join(extracted_dir, "dataset.json")):
        return extracted_dir

    tar_path = os.path.join(_DATA_ROOT, info["filename"])
    if not os.path.exists(tar_path):
        _download_file(info["url"], tar_path)

    print(f"解压: {tar_path}")
    with tarfile.open(tar_path, "r:gz") as tar:
        tar.extractall(_DATA_ROOT)
        members = tar.getnames()
        if members:
            top_dir = members[0].split("/")[0]
            result_dir = os.path.join(_DATA_ROOT, top_dir)
            if os.path.normpath(result_dir) != os.path.normpath(extracted_dir):
                if os.path.exists(extracted_dir):
                    shutil.rmtree(extracted_dir)
                shutil.move(result_dir, extracted_dir)

    return extracted_dir


# ============================================================================
# 指标收集 — 从 Agent 事件流中提取
# ============================================================================


@dataclass
class TaskMetrics:
    """单个任务的运行指标"""
    tool_calls: int = 0                       # 工具调用总次数
    tool_errors: int = 0                      # 工具执行失败次数
    tool_names: list[str] = field(default_factory=list)  # 每次调用的工具名
    tool_results: list[dict] = field(default_factory=list)  # 每次调用的结果摘要
    llm_calls: int = 0                        # LLM 调用次数（= agent loop 轮数）
    tokens_input: int = 0                     # 输入 token
    tokens_output: int = 0                    # 输出 token
    text_length: int = 0                      # Agent 文本回复长度
    agent_errors: list[str] = field(default_factory=list)  # EvError 消息
    duration_ms: int = 0                      # 运行耗时（毫秒）

    def to_dict(self) -> dict:
        return {
            "tool_calls": self.tool_calls,
            "tool_errors": self.tool_errors,
            "tool_names": self.tool_names,
            "llm_calls": self.llm_calls,
            "tokens_input": self.tokens_input,
            "tokens_output": self.tokens_output,
            "tokens_total": self.tokens_input + self.tokens_output,
            "text_length": self.text_length,
            "agent_errors": self.agent_errors,
            "duration_ms": self.duration_ms,
        }


class MetricsCollector:
    """从 Agent 事件流中收集指标"""

    def __init__(self, verbose: bool = True) -> None:
        self.metrics = TaskMetrics()
        self._in_llm_call = False
        self._got_text = False
        self._verbose = verbose

    def on_event(self, event: Any) -> None:
        m = self.metrics
        name = type(event).__name__

        if name == "EvTextStart":
            if not self._got_text:
                m.llm_calls += 1
                self._got_text = True
        elif name == "EvTextEnd":
            m.text_length += len(event.full_text)
            self._got_text = False
            if self._verbose:
                text = event.full_text
                print(f"           [LLM #{m.llm_calls}] 文本回复: {text[:200]}")
        elif name == "EvToolCallStart":
            if not self._got_text:
                m.llm_calls += 1
            m.tool_calls += 1
            m.tool_names.append(event.name)
        elif name == "EvToolCallProgress":
            if self._verbose:
                print(f"           >> {event.message}")
        elif name == "EvToolCallEnd":
            result_summary = None
            if event.error:
                m.tool_errors += 1
                result_summary = {"error": event.error}
                if self._verbose:
                    print(f"           [FAIL] {event.name}: {event.error[:200]}")
            elif event.result:
                r = str(event.result)
                result_summary = {"ok": r[:200]} if len(r) > 200 else {"ok": r}
                if self._verbose:
                    print(f"           [OK]   {event.name}: {r[:150]}")
            else:
                if self._verbose:
                    print(f"           [OK]   {event.name}")
                r = str(event.result)
                result_summary = {"ok": r[:200]} if len(r) > 200 else {"ok": r}
            m.tool_results.append(result_summary or {"ok": None})
        elif name == "EvError":
            m.agent_errors.append(event.message)
            if self._verbose:
                print(f"           [ERR]  {event.message}")


# ============================================================================
# Agent 初始化 — 完全复用项目现有组件
# ============================================================================


def _create_engine(
    model: str,
    api_key: str,
    base_url: str | None,
    thinking_budget: int = 0,
) -> AgentEngine:
    """创建 AgentEngine，使用项目的真实工具"""
    config = LLMConfig(
        model=model,
        api_key=api_key,
        base_url=base_url,
        temperature=0.0,
        max_tokens=8192,
        thinking_budget=thinking_budget,
    )

    llm = LLMProvider(config)

    tools = ToolRegistry()
    for tool in create_default_tools():
        tools.register(tool)

    prompt = PromptBuilder()
    hooks = HookManager()

    return AgentEngine(llm=llm, tools=tools, prompt=prompt, hooks=hooks)


# ============================================================================
# 单任务运行
# ============================================================================


async def _run_task(
    engine: AgentEngine,
    task: dict,
    dataset_dir: str,
    output_dir: str,
) -> tuple[dict, TaskMetrics]:
    """运行单个任务，返回 (test_case 文件复制结果, 指标)

    对 test case 1 走完整 agent 流程，test case 2/3 复用第一次的 agent 行为
    但由于 agent 是有状态的（会修改文件），需要对每个 test case 分别运行。
    """
    task_id = str(task["id"])
    instruction = task["instruction"]
    spreadsheet_dir = os.path.join(dataset_dir, task["spreadsheet_path"])

    os.makedirs(output_dir, exist_ok=True)

    # ---- 运行 test case 1（完整 agent 调用）----
    tc1_input = os.path.join(spreadsheet_dir, f"1_{task_id}_init.xlsx")
    tc1_output = os.path.join(output_dir, f"1_{task_id}_output.xlsx")

    if not os.path.exists(tc1_input):
        metrics = TaskMetrics()
        metrics.agent_errors.append(f"输入文件不存在: {tc1_input}")
        return {"1": False}, metrics

    # 复制 input → working（agent 直接操作 working 文件）
    working_dir = os.path.join(output_dir, "_working")
    os.makedirs(working_dir, exist_ok=True)
    working_file = os.path.join(working_dir, f"1_{task_id}.xlsx")
    shutil.copy2(tc1_input, working_file)

    # 构造用户消息
    user_msg = _USER_PROMPT_TEMPLATE.format(
        instruction=instruction,
        file_path=os.path.abspath(working_file),
    )

    # 创建 AgentEngine 并运行
    collector = MetricsCollector()
    state = ConversationState(session_id=f"bench_{task_id}")

    t_start = time.perf_counter()
    try:
        state = await engine.chat(state, user_msg, on_event=collector.on_event, max_steps=15)
    except Exception as e:
        collector.metrics.agent_errors.append(f"Agent 异常: {e}")
    t_end = time.perf_counter()

    collector.metrics.duration_ms = int((t_end - t_start) * 1000)
    collector.metrics.tokens_input = state.total_tokens  # 从 state 获取 token
    # 注意: state.total_tokens 是累积的，包含 input+output

    # 复制 working → output
    if os.path.exists(working_file):
        shutil.copy2(working_file, tc1_output)

    tc_results = {"1": os.path.exists(tc1_output)}

    # 清理 working
    if os.path.exists(working_dir):
        shutil.rmtree(working_dir, ignore_errors=True)

    return tc_results, collector.metrics


# ============================================================================
# 主流程
# ============================================================================


async def run_benchmark(args: argparse.Namespace) -> None:
    # 1. 准备数据集
    dataset_dir = ensure_dataset(args.dataset)
    dataset_json_path = os.path.join(dataset_dir, "dataset.json")

    if not os.path.exists(dataset_json_path):
        print(f"错误: 数据集配置不存在: {dataset_json_path}")
        sys.exit(1)

    with open(dataset_json_path, "r", encoding="utf-8") as f:
        tasks = json.load(f)

    total_available = len(tasks)
    max_tasks = args.max_tasks if args.max_tasks > 0 else total_available
    skip = args.skip if args.skip > 0 else 0
    tasks = tasks[skip:skip + max_tasks]

    print(f"\n{'='*60}")
    print("SpreadsheetBench 跑分 — Exceler Agent 模式")
    print(f"{'='*60}")
    print(f"数据集:    {args.dataset} ({total_available} 任务, 从第 {skip+1} 个开始, 评测 {len(tasks)} 个)")
    print(f"模型:      {args.model}")
    print(f"输出:      {args.output_dir}")
    print()

    # 2. 创建 AgentEngine（所有任务共用）
    engine = _create_engine(args.model, args.api_key, args.base_url, args.thinking)

    output_dir = os.path.join(args.output_dir, "outputs")
    os.makedirs(output_dir, exist_ok=True)

    # 3. 逐任务运行
    all_metrics: list[TaskMetrics] = []
    pbar_total = len(tasks)

    for i, task in enumerate(tasks):
        task_id = str(task["id"])
        prefix = f"[{i+1}/{pbar_total}] #{task_id}"
        print(f"{prefix} {task['instruction'][:50]}...")

        tc_results, metrics = await _run_task(engine, task, dataset_dir, output_dir)
        all_metrics.append(metrics)

        # 实时打印工具调用情况
        tools_str = ", ".join(metrics.tool_names) if metrics.tool_names else "无"
        errs = f" | 错误: {metrics.tool_errors}" if metrics.tool_errors else ""
        print(f"         工具({metrics.tool_calls}): [{tools_str}]{errs}  {metrics.duration_ms}ms")

    # 4. 评测
    print(f"\n{'─'*60}")
    print("评测中...")
    eval_results = evaluate_dataset(dataset_dir, output_dir, tasks)

    # 5. 报告
    print_report(eval_results, args.model, args.dataset, max_tasks)

    # 6. 指标汇总
    total_tool_calls = sum(m.tool_calls for m in all_metrics)
    total_tool_errors = sum(m.tool_errors for m in all_metrics)
    total_tokens = sum(m.tokens_input for m in all_metrics)
    total_llm_calls = sum(m.llm_calls for m in all_metrics)
    avg_duration = sum(m.duration_ms for m in all_metrics) / len(all_metrics) if all_metrics else 0

    # 工具使用频率
    tool_freq: dict[str, int] = {}
    for m in all_metrics:
        for name in m.tool_names:
            tool_freq[name] = tool_freq.get(name, 0) + 1

    print(f"\n{'='*60}")
    print("Agent 运行指标")
    print(f"{'='*60}")
    print(f"LLM 调用总数:      {total_llm_calls}")
    print(f"工具调用总数:       {total_tool_calls}")
    print(f"工具错误总数:       {total_tool_errors}")
    print(f"Token 消耗总量:     {total_tokens}")
    print(f"平均任务耗时:       {avg_duration:.0f}ms")
    print()
    print("工具调用频率:")
    for name, count in sorted(tool_freq.items(), key=lambda x: -x[1]):
        print(f"  {name}: {count}")

    # 错误分布
    error_tasks = sum(1 for m in all_metrics if m.agent_errors)
    error_tasks_with_tool_errors = sum(1 for m in all_metrics if m.tool_errors)
    print(f"\n任务级错误: {error_tasks}/{len(all_metrics)} 个任务有 agent 错误")
    print(f"工具执行失败: {error_tasks_with_tool_errors}/{len(all_metrics)} 个任务有工具执行错误")

    # 7. 保存完整报告
    report = {
        "model": args.model,
        "dataset": args.dataset,
        "total_tasks": len(eval_results),
        "soft_pass_count": sum(1 for r in eval_results if r["soft_restriction"] > 0),
        "hard_pass_count": sum(1 for r in eval_results if r["hard_restriction"] == 1),
        "soft_pass_rate": round(
            sum(1 for r in eval_results if r["soft_restriction"] > 0) / len(eval_results), 4
        ) if eval_results else 0,
        "hard_pass_rate": round(
            sum(1 for r in eval_results if r["hard_restriction"] == 1) / len(eval_results), 4
        ) if eval_results else 0,
        "agent_metrics": {
            "total_llm_calls": total_llm_calls,
            "total_tool_calls": total_tool_calls,
            "total_tool_errors": total_tool_errors,
            "total_tokens": total_tokens,
            "avg_duration_ms": round(avg_duration),
            "tool_frequency": tool_freq,
        },
        "tasks": [],
    }

    for eval_r, metrics in zip(eval_results, all_metrics):
        report["tasks"].append({
            **eval_r,
            "metrics": metrics.to_dict(),
        })

    report_path = os.path.join(args.output_dir, "report.json")
    save_report(eval_results, args.model, args.dataset, report_path)

    # 追加 agent 指标到报告
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2, default=str)

    print(f"\n完整报告已保存: {os.path.abspath(report_path)}")
    print(f"{'='*60}")


# ============================================================================
# CLI
# ============================================================================


def main() -> None:
    parser = argparse.ArgumentParser(
        description="SpreadsheetBench 跑分 — Exceler Agent 模式",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""\
示例:
  python -m python.benchmark.runner --model claude-sonnet-4-20250514 --api-key sk-ant-xxx
  python -m python.benchmark.runner --model claude-sonnet-4-20250514 --api-key sk-ant-xxx --max-tasks 10
  python -m python.benchmark.runner --model claude-sonnet-4-20250514 --api-key sk-ant-xxx --base-url https://your-proxy.example.com
""",
    )
    parser.add_argument("--model", required=True, help="LLM 模型名")
    parser.add_argument("--api-key", default="", help="API Key")
    parser.add_argument("--base-url", default=None, help="自定义 API 地址")
    parser.add_argument(
        "--dataset", default="verified_400",
        help="数据集名称 (spreadsheetbench_912|verified_400) 或本地路径",
    )
    parser.add_argument("--max-tasks", type=int, default=0, help="最多评测任务数（0=全部）")
    parser.add_argument("--skip", type=int, default=0, help="跳过前 N 个任务（从第 N+1 个开始）")
    parser.add_argument("--thinking", type=int, default=10000, help="extended thinking budget tokens (0=off, default=10000)")
    parser.add_argument(
        "--output-dir", default=os.path.join("data", "benchmark_outputs"),
        help="输出目录",
    )

    args = parser.parse_args()
    asyncio.run(run_benchmark(args))


if __name__ == "__main__":
    main()
