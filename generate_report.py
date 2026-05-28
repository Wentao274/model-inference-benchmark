import os
import sys
import re
import glob
import yaml
import argparse
from pathlib import Path
from datetime import datetime
from collections import defaultdict

try:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    HAS_MATPLOTLIB = True
except ImportError:
    HAS_MATPLOTLIB = False
    plt = None
    print("matplotlib not available, skipping chart generation")


def load_test_suites(config_path="config/test_suites.yaml"):
    if os.path.exists(config_path):
        with open(config_path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f)
    return {}


def load_chip_config(config_path="config/chip_conf.yaml"):
    if os.path.exists(config_path):
        with open(config_path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f)
    return {}


def load_deployment_config(config_path="config/model_deployment.yaml"):
    if os.path.exists(config_path):
        with open(config_path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f)
    return {}


def parse_benchmark_log(log_file, infra="vllm"):
    with open(log_file, "r", encoding="utf-8", errors="ignore") as f:
        content = f.read()

    lines = content.split("\n")
    metrics = {}

    section = None
    section_patterns = {
        "Serving Benchmark Result": "=========== Serving Benchmark Result",
        "End-to-End Latency": "----------------End-to-End Latency",
        "Time to First Token": "---------------Time to First Token",
        "Time per Output Token": "-----Time per Output Token",
        "Inter-Token Latency": "---------------Inter-Token Latency",
    }

    for line in lines:
        found_section = None
        for sec_name, sec_pattern in section_patterns.items():
            if sec_pattern in line:
                found_section = sec_name
                break

        if found_section:
            section = found_section
            continue

        if section and line.strip().startswith("==========="):
            section = None
            continue

        if section:
            match = re.match(r"(.+?):\s+(.+)$", line.strip())
            if match:
                key = match.group(1).strip()
                value = match.group(2).strip()
                if infra == "sglang":
                    full_key = f"[{section}] {key}"
                    metrics[full_key] = value
                metrics[key] = value

    if "failed requests" not in metrics:
        metrics["failed requests"] = "0"

    return metrics


def extract_concurrency_from_dir(dir_name):
    match = re.match(r"^(\d+)-", dir_name)
    if match:
        return match.group(1)
    return None


def extract_io_pair_from_dir(dir_name):
    match = re.search(r"-i(\d+)-o(\d+)", dir_name)
    if match:
        return match.group(1), match.group(2)
    return None, None


def get_all_concurrencies(base_path, run_id):
    concurrency_set = set()
    full_path = os.path.join(base_path, run_id)

    if not os.path.exists(full_path):
        return []

    for item in os.listdir(full_path):
        item_path = os.path.join(full_path, item)
        if os.path.isdir(item_path):
            conc = extract_concurrency_from_dir(item)
            if conc:
                concurrency_set.add(conc)

    return sorted(concurrency_set, key=lambda x: int(x))


def get_all_io_pairs(base_path, run_id, concurrency):
    io_pairs = set()
    full_path = os.path.join(base_path, run_id)

    if not os.path.exists(full_path):
        return []

    for item in os.listdir(full_path):
        item_path = os.path.join(full_path, item)
        if os.path.isdir(item_path):
            dir_concurrency = extract_concurrency_from_dir(item)
            if dir_concurrency == concurrency:
                input_len, output_len = extract_io_pair_from_dir(item)
                if input_len and output_len:
                    io_pairs.add((input_len, output_len))

    return sorted(io_pairs, key=lambda x: (int(x[0]), int(x[1])))


def get_io_lengths(base_path, run_id):
    io_pairs = set()
    full_path = os.path.join(base_path, run_id)

    if not os.path.exists(full_path):
        return [], []

    for item in os.listdir(full_path):
        item_path = os.path.join(full_path, item)
        if os.path.isdir(item_path):
            input_len, output_len = extract_io_pair_from_dir(item)
            if input_len and output_len:
                io_pairs.add((int(input_len), int(output_len)))

    if io_pairs:
        input_lens = sorted(set(p[0] for p in io_pairs))
        output_lens = sorted(set(p[1] for p in io_pairs))
        return input_lens, output_lens

    return [], []


def get_chip_metrics(base_path, run_id, concurrency, io_pair=None):
    full_path = os.path.join(base_path, run_id)

    if not os.path.exists(full_path):
        print(f"Warning: Path does not exist: {full_path}")
        return None

    for item in os.listdir(full_path):
        item_path = os.path.join(full_path, item)
        if os.path.isdir(item_path):
            if item.startswith(f"{concurrency}-"):
                log_files = glob.glob(os.path.join(item_path, "*.log"))
                if log_files:
                    return parse_benchmark_log(log_files[0])

    return None


def calculate_diff(val1, val2):
    try:
        f1 = float(val1)
        f2 = float(val2)
        diff = f2 - f1
        if f1 != 0:
            pct = (diff / f1) * 100
            return diff, pct
        return diff, 0
    except:
        return None, None


def generate_benchmark_command(infra, model_name, test_suite):
    test_suites = load_test_suites()
    suite_config = (
        test_suites.get("test-config", {}).get("suites", {}).get(test_suite, {})
    )

    dataset_name = suite_config.get("dataset-name", "random")
    max_concurrency = suite_config.get("max-concurrency", [1])
    num_prompts = suite_config.get("num-prompts", [128])
    random_input_output_len = suite_config.get(
        "random-input-output-len", [[50000, 200]]
    )

    nc = max_concurrency[0]
    np = num_prompts[0]
    ni = random_input_output_len[0][0]
    no = random_input_output_len[0][1]
    temperature = test_suites.get("test-config", {}).get("temperature", 0.7)
    seed = test_suites.get("test-config", {}).get("seed", 123)
    random_range_ratio = test_suites.get("test-config", {}).get(
        "random-range-ratio", 0.3
    )
    ready_timeout = test_suites.get("test-config", {}).get(
        "ready-check-timeout-sec", 30
    )

    if infra == "vllm":
        cmd_parts = [
            "vllm bench serve",
            "  --backend openai-chat",
            "  --endpoint /v1/chat/completions",
            f"  --dataset-name {dataset_name}",
            f"  --random-input-len {ni}",
            f"  --random-output-len {no}",
            f"  --random-range-ratio {random_range_ratio}",
            "  --model ${MODEL_PATH}",
            "  --trust-remote-code",
            "  --base-url ${BASE_URL}",
            f"  --num-prompts {np}",
            f"  --max-concurrency {nc}",
            f"  --temperature {temperature}",
            f"  --seed {seed}",
            "  --metric_percentiles 95,99",
            f"  --served-model-name {model_name}",
            f"  --ready-check-timeout-sec {ready_timeout}",
        ]
    else:
        cmd_parts = [
            "python3 -m sglang.bench_serving",
            "  --backend sglang-oai-chat",
            "  --base-url ${BASE_URL}",
            f"  --dataset-name {dataset_name}",
            f"  --random-range-ratio {random_range_ratio}",
            f"  --served-model-name {model_name}",
            f"  --random-input-len {ni}",
            f"  --random-output-len {no}",
            f"  --max-concurrency {nc}",
            f"  --num-prompt {np}",
            f"  --seed {seed}",
            "  --model ${MODEL_PATH}",
        ]

    return "\n".join(cmd_parts)


def format_diff(diff, pct):
    if diff is None:
        return "N/A", "N/A"
    if pct is not None:
        sign = "+" if diff > 0 else ""
        return f"{sign}{diff:.2f}", f"{sign}{pct:.1f}%"
    return f"{diff:.2f}", "N/A"


def generate_single_report(
    infra,
    chip_name,
    model_name,
    test_suite,
    run_id,
    base_path,
    concurrencies,
    output_dir,
):
    print(f"\nGenerating single run report for {run_id}...")

    input_lens, output_lens = get_io_lengths(base_path, run_id)

    chip_data = defaultdict(dict)
    for conc in concurrencies:
        metrics = get_chip_metrics(base_path, run_id, conc)
        if metrics:
            normalized_metrics = {}
            for key, value in metrics.items():
                normalized_metrics[key.lower()] = value
            chip_data[chip_name][conc] = normalized_metrics

    generate_single_csv(chip_data, concurrencies, output_dir, chip_name, infra)
    generate_single_charts(
        chip_data, concurrencies, output_dir, chip_name, model_name, infra
    )
    generate_single_markdown(
        chip_data,
        concurrencies,
        output_dir,
        chip_name,
        model_name,
        test_suite,
        infra,
        input_lens,
        output_lens,
    )


def generate_comparison_report(
    infra,
    chip_name,
    model_name,
    test_suite,
    run_ids,
    base_path,
    concurrencies,
    output_dir,
):
    if len(run_ids) == 2:
        print(f"\nGenerating comparison report for {run_ids[0]} vs {run_ids[1]}...")
    else:
        print(
            f"\nGenerating comparison report for {len(run_ids)} run-ids: {', '.join(run_ids)}..."
        )

    input_lens, output_lens = get_io_lengths(base_path, run_ids[0])

    runid_data = defaultdict(lambda: defaultdict(dict))
    for run_id in run_ids:
        for conc in concurrencies:
            metrics = get_chip_metrics(base_path, run_id, conc)
            if metrics:
                normalized_metrics = {}
                for key, value in metrics.items():
                    normalized_metrics[key.lower()] = value
                runid_data[run_id][chip_name][conc] = normalized_metrics

    generate_comparison_csv(
        runid_data, concurrencies, output_dir, chip_name, run_ids, infra
    )
    generate_comparison_charts(
        runid_data, concurrencies, output_dir, chip_name, model_name, run_ids, infra
    )
    generate_comparison_markdown(
        runid_data,
        concurrencies,
        output_dir,
        chip_name,
        model_name,
        test_suite,
        run_ids,
        infra,
        input_lens,
        output_lens,
    )


def generate_single_csv(chip_data, concurrencies, output_dir, chip_name, infra):
    if infra == "vllm":
        metric_names = [
            ("[Serving Benchmark Result]", ""),
            ("successful requests", "successful requests"),
            ("failed requests", "failed requests"),
            ("benchmark duration (s)", "benchmark duration (s)"),
            ("Total input tokens", "Total input tokens"),
            ("Total generated tokens", "Total generated tokens"),
            ("request throughput (req/s)", "request throughput (req/s)"),
            ("output token throughput (tok/s)", "output token throughput (tok/s)"),
            ("total token throughput (tok/s)", "total token throughput (tok/s)"),
            ("[Time to First Token]", ""),
            ("mean ttft (ms)", "mean ttft (ms)"),
            ("p99 ttft (ms)", "p99 ttft (ms)"),
            ("[Time per Output Token]", ""),
            ("mean tpot (ms)", "mean tpot (ms)"),
            ("p99 tpot (ms)", "p99 tpot (ms)"),
        ]
    else:
        metric_names = [
            ("[Serving Benchmark Result]", ""),
            ("successful requests", "successful requests"),
            ("benchmark duration (s)", "benchmark duration (s)"),
            ("Total input tokens", "Total input tokens"),
            ("Total generated tokens", "Total generated tokens"),
            ("request throughput (req/s)", "request throughput (req/s)"),
            ("output token throughput (tok/s)", "output token throughput (tok/s)"),
            ("total token throughput (tok/s)", "total token throughput (tok/s)"),
            ("[End-to-End Latency]", ""),
            ("mean e2e latency (ms)", "mean e2e latency (ms)"),
            ("p99 e2e latency (ms)", "p99 e2e latency (ms)"),
            ("[Time to First Token]", ""),
            ("mean ttft (ms)", "mean ttft (ms)"),
            ("p99 ttft (ms)", "p99 ttft (ms)"),
            ("[Time per Output Token]", ""),
            ("mean tpot (ms)", "mean tpot (ms)"),
            ("p99 tpot (ms)", "p99 tpot (ms)"),
        ]

    csv_lines = []
    header = ["Metric"] + [f"{conc}" for conc in concurrencies]
    csv_lines.append(",".join(header))

    for display_name, key_name in metric_names:
        if not key_name:
            csv_lines.append(f"[{display_name}]" + ",," * (len(concurrencies) - 1))
            continue
        row = [display_name]
        for conc in concurrencies:
            value = chip_data.get(chip_name, {}).get(conc, {}).get(key_name, "")
            row.append(value)
        csv_lines.append(",".join(row))

    csv_file = os.path.join(output_dir, "performance_trends.csv")
    with open(csv_file, "w", encoding="utf-8") as f:
        f.write("\n".join(csv_lines))
    print(f"Generated: {csv_file}")


def generate_single_charts(
    chip_data, concurrencies, output_dir, chip_name, model_name, infra
):
    if not HAS_MATPLOTLIB:
        return

    x = range(len(concurrencies))

    def get_values(key):
        values = []
        for conc in concurrencies:
            val = chip_data.get(chip_name, {}).get(conc, {}).get(key, "0")
            try:
                values.append(float(val))
            except:
                values.append(0)
        return values

    colors = ["#0066ff", "#00cc66", "#ff3366", "#ff9900", "#9933ff"]

    if infra == "vllm":
        metrics = [
            (
                "Request Throughput (req/s)",
                "request throughput (req/s)",
                "req/s",
                "{:.2f}",
            ),
            (
                "Output Token Throughput (tok/s)",
                "output token throughput (tok/s)",
                "tok/s",
                "{:.0f}",
            ),
            (
                "Total Token Throughput (tok/s)",
                "total token throughput (tok/s)",
                "tok/s",
                "{:.0f}",
            ),
            ("TTFT P99 (ms)", "p99 ttft (ms)", "ms", "{:.0f}"),
            ("TPOT P99 (ms)", "p99 tpot (ms)", "ms", "{:.2f}"),
            ("ITL P99 (ms)", "p99 itl (ms)", "ms", "{:.2f}"),
        ]
    else:
        metrics = [
            (
                "Request Throughput (req/s)",
                "request throughput (req/s)",
                "req/s",
                "{:.2f}",
            ),
            (
                "Output Token Throughput (tok/s)",
                "output token throughput (tok/s)",
                "tok/s",
                "{:.0f}",
            ),
            (
                "Total Token Throughput (tok/s)",
                "total token throughput (tok/s)",
                "tok/s",
                "{:.0f}",
            ),
            ("E2E Latency P99 (ms)", "p99 e2e latency (ms)", "ms", "{:.0f}"),
            ("TTFT P99 (ms)", "p99 ttft (ms)", "ms", "{:.0f}"),
            ("TPOT P99 (ms)", "p99 tpot (ms)", "ms", "{:.2f}"),
        ]

    fig, axes = plt.subplots(2, 3, figsize=(15, 10), constrained_layout=True)
    fig.suptitle(
        f"{model_name} on {chip_name} - Performance Trends",
        fontsize=14,
        fontweight="bold",
    )

    for idx, (title, key, ylabel, fmt) in enumerate(metrics):
        ax = axes[idx // 3, idx % 3]
        values = get_values(key)
        ax.plot(
            range(len(concurrencies)),
            values,
            "-o",
            color=colors[idx % len(colors)],
            linewidth=2,
            markersize=6,
        )

        for i, v in enumerate(values):
            if i % 2 == 0:
                xytext = (5, 8)
                ha = "left"
            else:
                xytext = (5, -12)
                ha = "left"
            ax.annotate(
                fmt.format(v),
                xy=(i, v),
                xytext=xytext,
                textcoords="offset points",
                fontsize=7,
                color=colors[idx % len(colors)],
                fontweight="bold",
                ha=ha,
                va="bottom" if i % 2 == 0 else "top",
                bbox=dict(
                    boxstyle="round,pad=0.2",
                    facecolor="white",
                    edgecolor="none",
                    alpha=0.7,
                ),
            )

        ax.set_title(title, fontsize=11)
        ax.set_xlabel("Concurrency")
        ax.set_ylabel(ylabel)
        ax.set_xticks(range(len(concurrencies)))
        ax.set_xticklabels(concurrencies, rotation=45)
        ax.grid(True, alpha=0.3)

    for ax in axes.flat:
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)

    chart_file = os.path.join(output_dir, "performance_trends.png")
    plt.savefig(chart_file, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"Generated chart: {chart_file}")


def generate_single_markdown(
    chip_data,
    concurrencies,
    output_dir,
    chip_name,
    model_name,
    test_suite,
    infra,
    input_lens=None,
    output_lens=None,
):
    if input_lens is None:
        input_lens = []
    if output_lens is None:
        output_lens = []

    current_date = datetime.now().strftime("%Y-%m-%d")

    framework_name = "vLLM" if infra == "vllm" else "SGLang"
    metric_suffix = "" if infra == "vllm" else " (E2E)"

    def get_value(conc, key):
        return chip_data.get(chip_name, {}).get(conc, {}).get(key, "N/A")

    header = " | ".join([f"{conc} 并发" for conc in concurrencies])
    separator = "----------- | " + " | ".join(["-----------"] * len(concurrencies))

    if infra == "vllm":
        serving_metrics = [
            ("成功请求数", "successful requests"),
            ("失败请求数", "failed requests"),
            ("测试持续时间 (s)", "benchmark duration (s)"),
            ("**请求吞吐量 (req/s)**", "request throughput (req/s)"),
            ("**输出 token 吞吐量 (tok/s)**", "output token throughput (tok/s)"),
            ("**总 token 吞吐量 (tok/s)**", "total token throughput (tok/s)"),
        ]
        ttft_metrics = [
            ("平均 TTFT (ms)", "mean ttft (ms)"),
            ("P99 TTFT (ms)", "p99 ttft (ms)"),
        ]
        tpot_metrics = [
            ("平均 TPOT (ms)", "mean tpot (ms)"),
            ("P99 TPOT (ms)", "p99 tpot (ms)"),
        ]
        itl_metrics = [
            ("平均 ITL (ms)", "mean itl (ms)"),
            ("p99 itl (ms)", "p99 itl (ms)"),
        ]
    else:
        serving_metrics = [
            ("成功请求数", "successful requests"),
            ("测试持续时间 (s)", "benchmark duration (s)"),
            ("**请求吞吐量 (req/s)**", "request throughput (req/s)"),
            ("**输入 token 吞吐量 (tok/s)**", "input token throughput (tok/s)"),
            ("**输出 token 吞吐量 (tok/s)**", "output token throughput (tok/s)"),
            ("**总 token 吞吐量 (tok/s)**", "total token throughput (tok/s)"),
        ]
        ttft_metrics = [
            ("平均 TTFT (ms)", "mean ttft (ms)"),
            ("P99 TTFT (ms)", "p99 ttft (ms)"),
        ]
        tpot_metrics = [
            ("平均 TPOT (ms)", "mean tpot (ms)"),
            ("P99 TPOT (ms)", "p99 tpot (ms)"),
        ]
        e2e_metrics = [
            ("平均 E2E 延迟 (ms)", "mean e2e latency (ms)"),
            ("P99 E2E 延迟 (ms)", "p99 e2e latency (ms)"),
        ]

    def make_table(metrics_list):
        rows = [f"| 指标 | {header} |", f"| {separator} |"]
        for name, key in metrics_list:
            row = [f"| {name} |"]
            for conc in concurrencies:
                row.append(f" {get_value(conc, key)} |")
            rows.append("".join(row))
        return "\n".join(rows)

    input_ctx_str = ", ".join([str(i) for i in input_lens]) if input_lens else "N/A"
    output_ctx_str = ", ".join([str(o) for o in output_lens]) if output_lens else "N/A"

    md_content = f"""# {model_name}模型在{chip_name}上的Benchmark报告

<div align="center">
**测试日期：** {current_date}
**框架：** {framework_name}
</div>

---

## 测试概览

| 项目 | 配置 |
|------|------|
| **测试套件** | {test_suite} |
| **推理框架** | {framework_name} |
| **输入上下文长度** | {input_ctx_str} |
| **输出上下文长度** | {output_ctx_str} |
| **并发数** | {", ".join(concurrencies)} |
| **模型** | {model_name} |
| **被测芯片** | {chip_name} |

---

## 性能趋势图表

![Performance Trends](./performance_trends.png)

---

## 服务基准结果

{make_table(serving_metrics)}

## 首Token延迟 (TTFT)

{make_table(ttft_metrics)}

## 每Token生成时间 (TPOT)

{make_table(tpot_metrics)}
"""

    if infra == "sglang":
        md_content += f"""
## 端到端延迟 (E2E)

{make_table(e2e_metrics)}
"""

    md_content += f"""
---

## Benchmark 执行命令

```bash
{generate_benchmark_command(infra, model_name, test_suite)}
```

---

<div align="center">
*报告生成时间: {current_date}*
</div>
"""

    md_file = os.path.join(output_dir, f"{model_name}_{chip_name}_report.md")
    with open(md_file, "w", encoding="utf-8") as f:
        f.write(md_content)
    print(f"Generated: {md_file}")


def generate_comparison_csv(
    runid_data, concurrencies, output_dir, chip_name, run_ids, infra
):
    if infra == "vllm":
        metric_names = [
            ("[Serving Benchmark Result]", ""),
            ("successful requests", "successful requests"),
            ("failed requests", "failed requests"),
            ("request throughput (req/s)", "request throughput (req/s)"),
            ("output token throughput (tok/s)", "output token throughput (tok/s)"),
            ("total token throughput (tok/s)", "total token throughput (tok/s)"),
            ("[Time to First Token]", ""),
            ("mean ttft (ms)", "mean ttft (ms)"),
            ("p99 ttft (ms)", "p99 ttft (ms)"),
            ("[Time per Output Token]", ""),
            ("mean tpot (ms)", "mean tpot (ms)"),
            ("p99 tpot (ms)", "p99 tpot (ms)"),
            ("[Inter-Token Latency]", ""),
            ("mean itl (ms)", "mean itl (ms)"),
            ("p99 itl (ms)", "p99 itl (ms)"),
        ]
    else:
        metric_names = [
            ("[Serving Benchmark Result]", ""),
            ("successful requests", "successful requests"),
            ("request throughput (req/s)", "request throughput (req/s)"),
            ("output token throughput (tok/s)", "output token throughput (tok/s)"),
            ("total token throughput (tok/s)", "total token throughput (tok/s)"),
            ("[End-to-End Latency]", ""),
            ("mean e2e latency (ms)", "mean e2e latency (ms)"),
            ("p99 e2e latency (ms)", "p99 e2e latency (ms)"),
            ("[Time to First Token]", ""),
            ("mean ttft (ms)", "mean ttft (ms)"),
            ("p99 ttft (ms)", "p99 ttft (ms)"),
            ("[Time per Output Token]", ""),
            ("mean tpot (ms)", "mean tpot (ms)"),
            ("p99 tpot (ms)", "p99 tpot (ms)"),
        ]

    run_id1, run_id2 = run_ids[0], run_ids[1]
    csv_lines = []
    header_parts = ["Metric"]
    for conc in concurrencies:
        header_parts.extend(
            [f"{conc}-{run_id1}", f"{conc}-{run_id2}", f"{conc}-Diff", f"{conc}-%"]
        )
    csv_lines.append(",".join(header_parts))

    for display_name, key_name in metric_names:
        if not key_name:
            csv_lines.append(f"[{display_name}]" + ",," * (len(concurrencies) * 4))
            continue
        row = [display_name]
        for conc in concurrencies:
            val1 = (
                runid_data.get(run_id1, {})
                .get(chip_name, {})
                .get(conc, {})
                .get(key_name.lower(), "")
            )
            val2 = (
                runid_data.get(run_id2, {})
                .get(chip_name, {})
                .get(conc, {})
                .get(key_name.lower(), "")
            )
            row.append(val1)
            row.append(val2)
            diff, pct = calculate_diff(val1, val2)
            diff_str, pct_str = format_diff(diff, pct)
            row.append(diff_str)
            row.append(pct_str)
        csv_lines.append(",".join(row))

    csv_file = os.path.join(output_dir, "runid_comparison.csv")
    with open(csv_file, "w", encoding="utf-8") as f:
        f.write("\n".join(csv_lines))
    print(f"Generated: {csv_file}")


def generate_comparison_charts(
    runid_data, concurrencies, output_dir, chip_name, model_name, run_ids, infra
):
    if not HAS_MATPLOTLIB:
        return

    x = range(len(concurrencies))
    colors = ["#0066ff", "#00cc66", "#ff3366", "#ff9900", "#9933ff"]
    markers = ["o", "s", "^", "D", "v"]

    if infra == "vllm":
        metrics = [
            ("Request Throughput (req/s)", "request throughput (req/s)", "req/s"),
            (
                "Output Token Throughput (tok/s)",
                "output token throughput (tok/s)",
                "tok/s",
            ),
            ("TTFT P99 (ms)", "p99 ttft (ms)", "ms"),
            ("TPOT P99 (ms)", "p99 tpot (ms)", "ms"),
            ("ITL P99 (ms)", "p99 itl (ms)", "ms"),
        ]
    else:
        metrics = [
            ("Request Throughput (req/s)", "request throughput (req/s)", "req/s"),
            (
                "Output Token Throughput (tok/s)",
                "output token throughput (tok/s)",
                "tok/s",
            ),
            ("E2E Latency P99 (ms)", "p99 e2e latency (ms)", "ms"),
            ("TTFT P99 (ms)", "p99 ttft (ms)", "ms"),
            ("TPOT P99 (ms)", "p99 tpot (ms)", "ms"),
        ]

    def get_values(run_id, key):
        values = []
        for conc in concurrencies:
            val = (
                runid_data.get(run_id, {})
                .get(chip_name, {})
                .get(conc, {})
                .get(key.lower(), "0")
            )
            try:
                values.append(float(val))
            except:
                values.append(0)
        return values

    num_plots = len(metrics)
    fig, axes = plt.subplots(
        2,
        (num_plots + 1) // 2,
        figsize=(5 * ((num_plots + 1) // 2), 10),
        constrained_layout=True,
    )
    axes = axes.flatten()
    if num_plots == 1:
        axes = [axes[0]]

    run_ids_str = (
        " vs ".join(run_ids) if len(run_ids) <= 2 else f"{len(run_ids)} Run-IDs"
    )
    fig.suptitle(
        f"{model_name} on {chip_name} - Run ID Comparison ({run_ids_str})",
        fontsize=14,
        fontweight="bold",
    )

    for idx, (title, key, ylabel) in enumerate(metrics):
        ax = axes[idx]

        for i, run_id in enumerate(run_ids):
            values = get_values(run_id, key)
            line_color = colors[i % len(colors)]
            ax.plot(
                x,
                values,
                marker=markers[i % len(markers)],
                markersize=6,
                label=run_id,
                color=line_color,
                linewidth=2,
            )

            for j, v in enumerate(values):
                if len(run_ids) == 1:
                    offset_x = 12
                    offset_y = 12
                elif len(run_ids) == 2:
                    if i == 0:
                        offset_x = 12
                        offset_y = 20
                    else:
                        offset_x = 12
                        offset_y = -22
                else:
                    if i == 0:
                        offset_x = 15
                        offset_y = 15
                    elif i == 1:
                        offset_x = 15
                        offset_y = -15
                    else:
                        offset_x = -45
                        offset_y = 15 if j % 2 == 0 else -15

                ax.annotate(
                    f"{v:.2f}" if v < 100 else f"{v:.0f}",
                    xy=(j, v),
                    xytext=(offset_x, offset_y),
                    textcoords="offset points",
                    fontsize=7,
                    color=line_color,
                    fontweight="bold",
                    bbox=dict(
                        boxstyle="round,pad=0.15",
                        facecolor="white",
                        edgecolor="none",
                        alpha=0.8,
                    ),
                    annotation_clip=False,
                )

        if len(run_ids) >= 2:
            baseline_values = get_values(run_ids[0], key)
            baseline_color = colors[0 % len(colors)]

            for i in range(1, len(run_ids)):
                compare_values = get_values(run_ids[i], key)
                compare_color = colors[i % len(colors)]

                for j in range(len(concurrencies)):
                    v1 = baseline_values[j]
                    v2 = compare_values[j]

                    try:
                        pct = ((v2 - v1) / v1) * 100 if v1 != 0 else 0
                        pct_str = f"{'+' if pct > 0 else ''}{pct:.1f}%"
                    except:
                        pct_str = "N/A"

                    ax.annotate(
                        "",
                        xy=(j, v2),
                        xytext=(j, v1),
                        arrowprops=dict(
                            arrowstyle="->",
                            color=compare_color,
                            lw=2,
                            connectionstyle="arc3,rad=0",
                        ),
                    )

                    pct_x = 25
                    pct_y = 0
                    if len(run_ids) == 2:
                        mid_y = (v1 + v2) / 2
                        if v2 >= v1:
                            pct_y = -20
                        else:
                            pct_y = 20
                        pct_xy = (j, mid_y)
                    else:
                        pct_xy = (j, (v1 + v2) / 2)
                        pct_y = 15 if j % 2 == 0 else -15
                        if i > 1:
                            pct_x = -40

                    ax.annotate(
                        pct_str,
                        xy=pct_xy,
                        xytext=(pct_x, pct_y),
                        textcoords="offset points",
                        fontsize=8,
                        color=compare_color,
                        fontweight="bold",
                        ha="left",
                        bbox=dict(
                            boxstyle="round,pad=0.2",
                            facecolor="white",
                            edgecolor=compare_color,
                            alpha=0.9,
                        ),
                        annotation_clip=False,
                    )

        ax.set_title(title, fontsize=11)
        ax.set_xlabel("Concurrency")
        ax.set_ylabel(ylabel)
        ax.set_xticks(x)
        ax.set_xticklabels(concurrencies, rotation=45)
        ax.legend(loc="best", fontsize=8)
        ax.grid(True, alpha=0.3)

        for ax in axes:
            ax.spines["top"].set_visible(False)
            ax.spines["right"].set_visible(False)

    for idx in range(num_plots, len(axes)):
        axes[idx].set_visible(False)

    chart_file = os.path.join(output_dir, "runid_comparison.png")
    plt.savefig(chart_file, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"Generated chart: {chart_file}")


def generate_comparison_markdown(
    runid_data,
    concurrencies,
    output_dir,
    chip_name,
    model_name,
    test_suite,
    run_ids,
    infra,
    input_lens=None,
    output_lens=None,
):
    if input_lens is None:
        input_lens = []
    if output_lens is None:
        output_lens = []

    current_date = datetime.now().strftime("%Y-%m-%d")
    framework_name = "vLLM" if infra == "vllm" else "SGLang"

    input_ctx_str = ", ".join([str(i) for i in input_lens]) if input_lens else "N/A"
    output_ctx_str = ", ".join([str(o) for o in output_lens]) if output_lens else "N/A"

    if infra == "vllm":
        serving_metrics = [
            ("**请求吞吐量 (req/s)**", "request throughput (req/s)"),
            ("**输出 token 吞吐量 (tok/s)**", "output token throughput (tok/s)"),
            ("**总 token 吞吐量 (tok/s)**", "total token throughput (tok/s)"),
        ]
        ttft_metrics = [
            ("平均 TTFT (ms)", "mean ttft (ms)"),
            ("P99 TTFT (ms)", "p99 ttft (ms)"),
        ]
        tpot_metrics = [
            ("平均 TPOT (ms)", "mean tpot (ms)"),
            ("P99 TPOT (ms)", "p99 tpot (ms)"),
        ]
        itl_metrics = [
            ("平均 ITL (ms)", "mean itl (ms)"),
            ("P99 ITL (ms)", "p99 itl (ms)"),
        ]
    else:
        serving_metrics = [
            ("**请求吞吐量 (req/s)**", "request throughput (req/s)"),
            ("**输出 token 吞吐量 (tok/s)**", "output token throughput (tok/s)"),
            ("**总 token 吞吐量 (tok/s)**", "total token throughput (tok/s)"),
        ]
        ttft_metrics = [
            ("平均 TTFT (ms)", "mean ttft (ms)"),
            ("P99 TTFT (ms)", "p99 ttft (ms)"),
        ]
        tpot_metrics = [
            ("平均 TPOT (ms)", "mean tpot (ms)"),
            ("P99 TPOT (ms)", "p99 tpot (ms)"),
        ]
        e2e_metrics = [
            ("平均 E2E 延迟 (ms)", "mean e2e latency (ms)"),
            ("P99 E2E 延迟 (ms)", "p99 e2e latency (ms)"),
        ]

    run_id1 = run_ids[0]
    run_id2 = run_ids[-1] if len(run_ids) > 1 else run_ids[0]
    run_ids_display = " vs ".join(run_ids)

    if len(run_ids) == 2:

        def make_table_for_conc(conc, key_name):
            val1 = (
                runid_data.get(run_id1, {})
                .get(chip_name, {})
                .get(conc, {})
                .get(key_name.lower(), "")
            )
            val2 = (
                runid_data.get(run_id2, {})
                .get(chip_name, {})
                .get(conc, {})
                .get(key_name.lower(), "")
            )
            diff, pct = calculate_diff(val1, val2)
            diff_str, pct_str = format_diff(diff, pct)
            return val1, val2, diff_str, pct_str

        header = f"| 指标 | RUN-{run_id1} | RUN-{run_id2} | 差异 | 百分比 |"
        separator = "|------|----------|---------|---------|---------|"

        def make_table(metrics_list):
            rows = [header, separator]
            for name, key in metrics_list:
                for conc in concurrencies:
                    val1, val2, diff_str, pct_str = make_table_for_conc(conc, key)
                    rows.append(
                        f"| {name} ({conc}并发) | {val1} | {val2} | {diff_str} | {pct_str} |"
                    )
            return "\n".join(rows)

        def calc_avg_improvement(key_name):
            improvements = []
            for conc in concurrencies:
                val1 = (
                    runid_data.get(run_id1, {})
                    .get(chip_name, {})
                    .get(conc, {})
                    .get(key_name.lower(), "")
                )
                val2 = (
                    runid_data.get(run_id2, {})
                    .get(chip_name, {})
                    .get(conc, {})
                    .get(key_name.lower(), "")
                )
                try:
                    v1, v2 = float(val1), float(val2)
                    if v1 > 0:
                        improvements.append(((v2 - v1) / v1) * 100)
                except:
                    pass
            return sum(improvements) / len(improvements) if improvements else 0

        improvements = {
            "tp": calc_avg_improvement("request throughput (req/s)"),
            "output_tp": calc_avg_improvement("output token throughput (tok/s)"),
            "ttft": calc_avg_improvement("p99 ttft (ms)"),
            "tpot": calc_avg_improvement("p99 tpot (ms)"),
        }

        analysis = f"""### 吞吐量对比

"""
        if improvements["tp"] > 0:
            analysis += f"**请求吞吐量**: RUN-{run_id2} 相比 RUN-{run_id1} 平均提升 **{improvements['tp']:.1f}%**\n\n"
        else:
            analysis += f"**请求吞吐量**: RUN-{run_id2} 相比 RUN-{run_id1} 平均变化 **{improvements['tp']:.1f}%**\n\n"

        if improvements["output_tp"] > 0:
            analysis += f"**输出Token吞吐量**: RUN-{run_id2} 相比 RUN-{run_id1} 平均提升 **{improvements['output_tp']:.1f}%**\n\n"
        else:
            analysis += f"**输出Token吞吐量**: RUN-{run_id2} 相比 RUN-{run_id1} 平均变化 **{improvements['output_tp']:.1f}%**\n\n"

        analysis += "### 延迟对比\n\n"
        if improvements["ttft"] > 0:
            analysis += f"**TTFT P99**: RUN-{run_id2} 相比 RUN-{run_id1} 平均增加 **{improvements['ttft']:.1f}%**\n\n"
        else:
            analysis += f"**TTFT P99**: RUN-{run_id2} 相比 RUN-{run_id1} 平均改善 **{abs(improvements['ttft']):.1f}%**\n\n"

        if improvements["tpot"] > 0:
            analysis += f"**TPOT P99**: RUN-{run_id2} 相比 RUN-{run_id1} 平均增加 **{improvements['tpot']:.1f}%**\n\n"
        else:
            analysis += f"**TPOT P99**: RUN-{run_id2} 相比 RUN-{run_id1} 平均改善 **{abs(improvements['tpot']):.1f}%**\n\n"

        tables_section = f"""
## 服务基准结果

{make_table(serving_metrics)}

## 首Token延迟 (TTFT)

{make_table(ttft_metrics)}

## 每Token生成时间 (TPOT)

{make_table(tpot_metrics)}
"""
        if infra == "sglang":
            tables_section += f"""
## 端到端延迟 (E2E)

{make_table(e2e_metrics)}
"""

        tables_section += f"""
---

## 分析总结

{analysis}
"""
    else:
        run_id1 = run_ids[0]
        run_ids_compare = run_ids[1:]

        header = (
            "| 指标 | RUN-"
            + run_id1
            + " | "
            + " | ".join([f"RUN-{rid} (vs {run_id1})" for rid in run_ids_compare])
            + " |"
        )
        num_cols = len(run_ids) + 1
        separator = "| " + " | ".join(["-" * 10 for _ in range(num_cols)]) + " |"

        def make_table(metrics_list):
            rows = [header, separator]
            for name, key in metrics_list:
                for conc in concurrencies:
                    row = [f"| {name} ({conc}并发) |"]
                    baseline_val = (
                        runid_data.get(run_id1, {})
                        .get(chip_name, {})
                        .get(conc, {})
                        .get(key.lower(), "")
                    )
                    row.append(f" {baseline_val} |")
                    for rid in run_ids_compare:
                        val = (
                            runid_data.get(rid, {})
                            .get(chip_name, {})
                            .get(conc, {})
                            .get(key.lower(), "")
                        )
                        diff, pct = calculate_diff(baseline_val, val)
                        diff_str, pct_str = format_diff(diff, pct)
                        row.append(f" {val} ({pct_str}) |")
                    rows.append("".join(row))
            return "\n".join(rows)

        def calc_avg_improvement(key_name):
            improvements = {}
            for rid in run_ids_compare:
                impr_list = []
                for conc in concurrencies:
                    val1 = (
                        runid_data.get(run_id1, {})
                        .get(chip_name, {})
                        .get(conc, {})
                        .get(key_name.lower(), "")
                    )
                    val2 = (
                        runid_data.get(rid, {})
                        .get(chip_name, {})
                        .get(conc, {})
                        .get(key_name.lower(), "")
                    )
                    try:
                        v1, v2 = float(val1), float(val2)
                        if v1 > 0:
                            impr_list.append(((v2 - v1) / v1) * 100)
                    except:
                        pass
                improvements[rid] = sum(impr_list) / len(impr_list) if impr_list else 0
            return improvements

        improvements = {
            "tp": calc_avg_improvement("request throughput (req/s)"),
            "output_tp": calc_avg_improvement("output token throughput (tok/s)"),
            "ttft": calc_avg_improvement("p99 ttft (ms)"),
            "tpot": calc_avg_improvement("p99 tpot (ms)"),
        }

        analysis = "### 吞吐量对比\n\n"
        for rid in run_ids_compare:
            tp = improvements["tp"].get(rid, 0)
            output_tp = improvements["output_tp"].get(rid, 0)
            direction_tp = "提升" if tp > 0 else "变化"
            direction_output = "提升" if output_tp > 0 else "变化"
            analysis += f"**请求吞吐量**: RUN-{rid} 相比 RUN-{run_id1} 平均{direction_tp} **{tp:.1f}%**\n\n"
            analysis += f"**输出Token吞吐量**: RUN-{rid} 相比 RUN-{run_id1} 平均{direction_output} **{output_tp:.1f}%**\n\n"

        analysis += "### 延迟对比\n\n"
        for rid in run_ids_compare:
            ttft = improvements["ttft"].get(rid, 0)
            tpot = improvements["tpot"].get(rid, 0)
            direction_ttft = "增加" if ttft > 0 else "改善"
            direction_tpot = "增加" if tpot > 0 else "改善"
            analysis += f"**TTFT P99**: RUN-{rid} 相比 RUN-{run_id1} 平均{direction_ttft} **{abs(ttft):.1f}%**\n\n"
            analysis += f"**TPOT P99**: RUN-{rid} 相比 RUN-{run_id1} 平均{direction_tpot} **{abs(tpot):.1f}%**\n\n"

        tables_section = f"""
## 服务基准结果

{make_table(serving_metrics)}

## 首Token延迟 (TTFT)

{make_table(ttft_metrics)}

## 每Token生成时间 (TPOT)

{make_table(tpot_metrics)}
"""
        if infra == "sglang":
            tables_section += f"""
## 端到端延迟 (E2E)

{make_table(e2e_metrics)}
"""

        if infra == "vllm":
            tables_section += f"""
## Token间延迟 (ITL)

{make_table(itl_metrics)}
"""

        tables_section += f"""
---

## 分析总结

{analysis}
"""

    md_content = f"""# {model_name}模型在{chip_name}上的Run-ID对比报告

<div align="center">
**测试日期：** {current_date}
**框架：** {framework_name}
**对比RUN-ID：** {run_ids_display}
</div>

---

## 测试概览

| 项目 | 配置 |
|------|------|
| **测试套件** | {test_suite} |
| **推理框架** | {framework_name} |
| **输入上下文长度** | {input_ctx_str} |
| **输出上下文长度** | {output_ctx_str} |
| **并发数** | {", ".join(concurrencies)} |
| **RUN-ID数量** | {len(run_ids)} |
| **模型** | {model_name} |
| **被测芯片** | {chip_name} |

---

## RUN-ID对比图表

![Run ID Comparison](./runid_comparison.png)

---

{tables_section}

---

## Benchmark 执行命令

```bash
{generate_benchmark_command(infra, model_name, test_suite)}
```

<div align="center">
*报告生成时间: {current_date}*
</div>
"""

    md_file = os.path.join(output_dir, f"{model_name}_{chip_name}_runid_compare.md")
    with open(md_file, "w", encoding="utf-8") as f:
        f.write(md_content)
    print(f"Generated: {md_file}")


def get_available_run_ids(infra, chip_name, model_name, test_suite):
    base_path = f"reports/{infra}/benchmark/{chip_name}/{model_name}/{test_suite}"
    if not os.path.exists(base_path):
        return []

    run_ids = []
    for item in os.listdir(base_path):
        item_path = os.path.join(base_path, item)
        if os.path.isdir(item_path):
            run_ids.append(item)

    return run_ids


def main():
    parser = argparse.ArgumentParser(description="Generate benchmark reports")
    parser.add_argument(
        "--infra",
        type=str,
        required=True,
        choices=["vllm", "sglang"],
        help="Infrastructure: vllm or sglang",
    )
    parser.add_argument(
        "--chip",
        type=str,
        required=True,
        help="Chip name (e.g., nvidia_h100, hygon_bw1000)",
    )
    parser.add_argument("--model", type=str, required=True, help="Model name")
    parser.add_argument(
        "--test-suite",
        type=str,
        default="test_01",
        help="Test suite name (default: test_01)",
    )
    parser.add_argument(
        "--run-id",
        type=str,
        default=None,
        help="Run ID to generate report for. If not specified, use the latest run-id.",
    )
    parser.add_argument(
        "--compare-with",
        type=str,
        default=None,
        help="Run ID(s) to compare with, comma-separated. Requires --run-id to be specified.",
    )
    args = parser.parse_args()

    if args.compare_with and not args.run_id:
        parser.error("--compare-with requires --run-id to be specified")

    chip_name = args.chip.lower()
    model_name = args.model
    test_suite = args.test_suite
    infra = args.infra

    print(f"\n{'=' * 60}")
    print(f"Report Generation Configuration")
    print(f"{'=' * 60}")
    print(f"Infra: {infra}")
    print(f"Chip: {chip_name}")
    print(f"Model: {model_name}")
    print(f"Test Suite: {test_suite}")
    if args.run_id:
        print(f"Target Run-ID: {args.run_id}")
    if args.compare_with:
        print(f"Compare with Run-ID: {args.compare_with}")
    print(f"{'=' * 60}\n")

    benchmark_path = f"reports/{infra}/benchmark/{chip_name}/{model_name}/{test_suite}"
    if not os.path.exists(benchmark_path):
        print(f"Error: Benchmark path not found: {benchmark_path}")
        return

    run_ids = get_available_run_ids(infra, chip_name, model_name, test_suite)
    if not run_ids:
        print(f"No run-id data found for test suite: {test_suite}")
        return

    run_ids_sorted = sorted(
        run_ids,
        key=lambda x: os.path.getmtime(
            os.path.join(
                f"reports/{infra}/benchmark/{chip_name}/{model_name}/{test_suite}", x
            )
        ),
        reverse=True,
    )
    print(f"Found {len(run_ids)} run-id(s): {', '.join(run_ids_sorted)}")

    base_path = f"reports/{infra}/benchmark/{chip_name}/{model_name}/{test_suite}"
    test_run_id = args.run_id or run_ids_sorted[0]
    concurrencies = get_all_concurrencies(base_path, test_run_id)

    if not concurrencies:
        print(f"No concurrency configurations found!")
        return

    print(f"Found {len(concurrencies)} concurrency levels: {', '.join(concurrencies)}")

    output_dir = None
    output_dirs = []
    if args.run_id:
        if args.compare_with:
            all_run_ids = [args.run_id] + [
                c.strip() for c in args.compare_with.split(",")
            ]
            all_run_ids = [r for r in all_run_ids if r != args.run_id]
            all_run_ids = [args.run_id] + all_run_ids
            compare_str = "_".join([r for r in all_run_ids if r != args.run_id])
            output_dir = f"analysis/{infra}/{chip_name}/{model_name}/{test_suite}/compare_{args.run_id}_{compare_str}"
            Path(output_dir).mkdir(parents=True, exist_ok=True)
            generate_comparison_report(
                infra,
                chip_name,
                model_name,
                test_suite,
                all_run_ids,
                base_path,
                concurrencies,
                output_dir,
            )
            output_dirs.append(output_dir)
        else:
            output_dir = (
                f"analysis/{infra}/{chip_name}/{model_name}/{test_suite}/{args.run_id}"
            )
            Path(output_dir).mkdir(parents=True, exist_ok=True)
            generate_single_report(
                infra,
                chip_name,
                model_name,
                test_suite,
                args.run_id,
                base_path,
                concurrencies,
                output_dir,
            )
            output_dirs.append(output_dir)
    else:
        latest_run_id = run_ids_sorted[0]
        if len(run_ids) == 1:
            output_dir = f"analysis/{infra}/{chip_name}/{model_name}/{test_suite}/{latest_run_id}"
            Path(output_dir).mkdir(parents=True, exist_ok=True)
            generate_single_report(
                infra,
                chip_name,
                model_name,
                test_suite,
                latest_run_id,
                base_path,
                concurrencies,
                output_dir,
            )
        else:
            if args.compare_with:
                compare_ids = [c.strip() for c in args.compare_with.split(",")]
                for compare_id in compare_ids:
                    run_ids_to_compare = [compare_id, latest_run_id]
                    output_dir = f"analysis/{infra}/{chip_name}/{model_name}/{test_suite}/compare_{compare_id}_{latest_run_id}"
                    Path(output_dir).mkdir(parents=True, exist_ok=True)
                    generate_comparison_report(
                        infra,
                        chip_name,
                        model_name,
                        test_suite,
                        run_ids_to_compare,
                        base_path,
                        concurrencies,
                        output_dir,
                    )
                    output_dirs.append(output_dir)
            else:
                compare_run_id = (
                    run_ids_sorted[1] if len(run_ids) >= 2 else run_ids_sorted[0]
                )

                run_ids_to_compare = [compare_run_id, latest_run_id]
                output_dir = f"analysis/{infra}/{chip_name}/{model_name}/{test_suite}/compare_{compare_run_id}_{latest_run_id}"
                Path(output_dir).mkdir(parents=True, exist_ok=True)
                generate_comparison_report(
                    infra,
                    chip_name,
                    model_name,
                    test_suite,
                    run_ids_to_compare,
                    base_path,
                    concurrencies,
                    output_dir,
                )
                output_dirs.append(output_dir)

    print(f"\n{'=' * 50}")
    print(f"Report generated successfully!")
    if output_dirs:
        print(f"Output directories:")
        for d in output_dirs:
            print(f"  - {d}")
    print(f"{'=' * 50}")


if __name__ == "__main__":
    main()
