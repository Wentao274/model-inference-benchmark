import os
import re
import glob
import yaml
import argparse
from datetime import datetime
from pathlib import Path


def parse_serve_command(serve_cmd):
    result = {}

    dp_patterns = [r"--dp-size\s+(\d+)", r"--dp\s+(\d+)", r"-dp\s+(\d+)"]
    for pattern in dp_patterns:
        match = re.search(pattern, serve_cmd)
        if match:
            result["dp"] = match.group(1)
            break

    tp_patterns = [r"--tp-size\s+(\d+)", r"--tp\s+(\d+)", r"-tp\s+(\d+)"]
    for pattern in tp_patterns:
        match = re.search(pattern, serve_cmd)
        if match:
            result["tp"] = match.group(1)
            break

    pp_patterns = [r"--pp-size\s+(\d+)", r"--pp\s+(\d+)", r"-pp\s+(\d+)"]
    for pattern in pp_patterns:
        match = re.search(pattern, serve_cmd)
        if match:
            result["pp"] = match.group(1)
            break

    ep_patterns = [r"--ep-size\s+(\d+)", r"--ep\s+(\d+)", r"-ep\s+(\d+)"]
    for pattern in ep_patterns:
        match = re.search(pattern, serve_cmd)
        if match:
            result["ep"] = match.group(1)
            break

    return result


def build_title_suffix(serve_cmd):
    parts = parse_serve_command(serve_cmd)
    suffix_parts = []

    if "dp" in parts:
        suffix_parts.append(f"dp{parts['dp']}")
    if "tp" in parts:
        suffix_parts.append(f"tp{parts['tp']}")
    if "pp" in parts:
        suffix_parts.append(f"pp{parts['pp']}")
    if "ep" in parts:
        suffix_parts.append(f"ep{parts['ep']}")

    return "".join(suffix_parts)


def parse_benchmark_log(log_file, infra="sglang"):
    with open(log_file, "r", encoding="utf-8", errors="ignore") as f:
        content = f.read()

    lines = content.split("\n")
    metrics = {}

    section = None
    if infra == "sglang":
        section_patterns = {
            "Serving": "=========== Serving Benchmark Result",
            "E2E Latency": "----------------End-to-End Latency",
            "TTFT": "---------------Time to First Token",
            "TPOT": "-----Time per Output Token",
            "ITL": "---------------Inter-Token Latency",
        }
    else:
        section_patterns = {
            "Serving": "============ Serving Benchmark Result",
            "TTFT": "---------------Time to First Token",
            "TPOT": "-----Time per Output Token",
            "ITL": "---------------Inter-Token Latency",
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

        if section:
            line_stripped = line.strip()
            if line_stripped.startswith("===") or line_stripped.startswith("---"):
                section = None
                continue

            match = re.match(r"(.+?):\s+(.+)$", line_stripped)
            if match:
                key = match.group(1).strip()
                value = match.group(2).strip()
                metrics[key] = value

    if "Failed requests" not in metrics:
        metrics["Failed requests"] = "0"

    return metrics


def load_test_suites(config_path="config/test_suites.yaml"):
    if os.path.exists(config_path):
        with open(config_path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f)
    return {}


def load_speed_bench_config():
    config_path = "config/test_suites_speed_bench.yaml"
    if os.path.exists(config_path):
        with open(config_path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f)
    return {}


def extract_concurrency_from_dir(dir_name):
    match = re.match(r"^(\d+)-", dir_name)
    if match:
        return match.group(1)
    return None


def extract_concurrency_num_prompts_from_dir(dir_name):
    match = re.match(r"c(\d+)-n(\d+)", dir_name)
    if match:
        return match.group(1), match.group(2)
    return None, None


def get_all_concurrencies_speed_bench(base_path):
    concurrency_set = set()
    num_prompts_set = set()

    if not os.path.exists(base_path):
        return [], []

    for round_dir in os.listdir(base_path):
        round_path = os.path.join(base_path, round_dir)
        if os.path.isdir(round_path):
            for item in os.listdir(round_path):
                item_path = os.path.join(round_path, item)
                if os.path.isdir(item_path):
                    conc, num_prompts = extract_concurrency_num_prompts_from_dir(item)
                    if conc:
                        concurrency_set.add(conc)
                    if num_prompts:
                        num_prompts_set.add(num_prompts)

    return sorted(concurrency_set, key=lambda x: int(x)), sorted(
        num_prompts_set, key=lambda x: int(x)
    )


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


def get_chip_metrics(base_path, run_id, concurrency, infra):
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
                    return parse_benchmark_log(log_files[0], infra)

    return None


def get_chip_metrics_speed_bench(base_path, round_id, concurrency, num_prompts, infra):
    full_path = os.path.join(base_path, round_id)

    if not os.path.exists(full_path):
        print(f"Warning: Path does not exist: {full_path}")
        return None

    target_dir = f"c{concurrency}-n{num_prompts}"
    target_path = os.path.join(full_path, target_dir)

    if os.path.isdir(target_path):
        log_files = glob.glob(os.path.join(target_path, "*.log"))
        if log_files:
            return parse_benchmark_log(log_files[0], infra)

    return None


def generate_benchmark_command(
    infra,
    model_name,
    model_path,
    test_suite,
    concurrency,
    base_url,
    dataset_type="random",
    subset=None,
):
    if dataset_type == "speed_bench":
        speed_bench_config = load_speed_bench_config()
        test_config = speed_bench_config.get("test-config", {})
        dataset_name = test_config.get("dataset-name", "speed_bench")
        dataset_path = test_config.get("dataset-path", "")
        output_len = test_config.get("speed-bench-output-len", 1024)
        temperature = test_config.get("temperature", 0.7)
        seed = test_config.get("seed", 123)
        ready_timeout = test_config.get("ready-check-timeout-sec", 30)
        num_prompts = test_config.get("num-prompts", [200])[0]

        if infra == "vllm":
            cmd_parts = [
                "vllm bench serve",
                "  --backend openai-chat",
                "  --endpoint /v1/chat/completions",
                f"  --dataset-name {dataset_name}",
                f"  --speed-bench-dataset-subset throughput_{subset}",
                f"  --dataset-path {dataset_path}",
                f"  --model {model_path}",
                "  --trust-remote-code",
                f"  --base-url {base_url}",
                f"  --num-prompts {num_prompts}",
                f"  --max-concurrency {concurrency}",
                f"  --speed-bench-output-len {output_len}",
                f"  --temperature {temperature}",
                f"  --seed {seed}",
                "  --metric_percentiles 95,99",
                f"  --served-model-name {model_name}",
                f"  --ready-check-timeout-sec {ready_timeout}",
            ]
        else:
            cmd_parts = [f"# speed_bench not supported for {infra}"]
    else:
        test_suites = load_test_suites()
        suite_config = (
            test_suites.get("test-config", {}).get("suites", {}).get(test_suite, {})
        )

        dataset_name = suite_config.get("dataset-name", "random")
        num_prompts = suite_config.get("num-prompts", [100])[0]
        random_input_output_len = suite_config.get(
            "random-input-output-len", [[50000, 200]]
        )[0]
        ni = random_input_output_len[0]
        no = random_input_output_len[1]
        temperature = test_suites.get("test-config", {}).get("temperature", 0.7)
        seed = test_suites.get("test-config", {}).get("seed", 123)
        random_range_ratio = test_suites.get("test-config", {}).get(
            "random-range-ratio", 0.0
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
                f"  --model {model_path}",
                "  --trust-remote-code",
                f"  --base-url {base_url}",
                f"  --num-prompts {num_prompts}",
                f"  --max-concurrency {concurrency}",
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
                f"  --base-url {base_url}",
                f"  --dataset-name {dataset_name}",
                f"  --random-range-ratio {random_range_ratio}",
                f"  --served-model-name {model_name}",
                f"  --random-input-len {ni}",
                f"  --random-output-len {no}",
                f"  --max-concurrency {concurrency}",
                f"  --num-prompt {num_prompts}",
                f"  --seed {seed}",
                f"  --model {model_path}",
            ]

    return "\n".join(cmd_parts)


def format_metrics_for_md(metrics, infra):
    if infra == "sglang":
        metric_keys = [
            ("Backend", "Backend"),
            ("Traffic request rate", "Traffic request rate"),
            ("Max request concurrency", "Max request concurrency"),
            ("Successful requests", "Successful requests"),
            ("Benchmark duration (s)", "Benchmark duration (s)"),
            ("Total input tokens", "Total input tokens"),
            ("Total generated tokens", "Total generated tokens"),
            ("Request throughput (req/s)", "Request throughput (req/s)"),
            ("Input token throughput (tok/s)", "Input token throughput (tok/s)"),
            ("Output token throughput (tok/s)", "Output token throughput (tok/s)"),
            (
                "Peak output token throughput (tok/s)",
                "Peak output token throughput (tok/s)",
            ),
            ("Peak concurrent requests", "Peak concurrent requests"),
            ("Total token throughput (tok/s)", "Total token throughput (tok/s)"),
            ("Concurrency", "Concurrency"),
            ("Mean E2E Latency (ms)", "Mean E2E Latency (ms)"),
            ("Median E2E Latency (ms)", "Median E2E Latency (ms)"),
            ("P90 E2E Latency (ms)", "P90 E2E Latency (ms)"),
            ("P99 E2E Latency (ms)", "P99 E2E Latency (ms)"),
            ("Mean TTFT (ms)", "Mean TTFT (ms)"),
            ("Median TTFT (ms)", "Median TTFT (ms)"),
            ("P99 TTFT (ms)", "P99 TTFT (ms)"),
            ("Mean TPOT (ms)", "Mean TPOT (ms)"),
            ("Median TPOT (ms)", "Median TPOT (ms)"),
            ("P99 TPOT (ms)", "P99 TPOT (ms)"),
            ("Mean ITL (ms)", "Mean ITL (ms)"),
            ("Median ITL (ms)", "Median ITL (ms)"),
            ("P95 ITL (ms)", "P95 ITL (ms)"),
            ("P99 ITL (ms)", "P99 ITL (ms)"),
            ("Max ITL (ms)", "Max ITL (ms)"),
        ]
    else:
        metric_keys = [
            ("Successful requests", "Successful requests"),
            ("Failed requests", "Failed requests"),
            ("Maximum request concurrency", "Maximum request concurrency"),
            ("Benchmark duration (s)", "Benchmark duration (s)"),
            ("Total input tokens", "Total input tokens"),
            ("Total generated tokens", "Total generated tokens"),
            ("Request throughput (req/s)", "Request throughput (req/s)"),
            ("Output token throughput (tok/s)", "Output token throughput (tok/s)"),
            (
                "Peak output token throughput (tok/s)",
                "Peak output token throughput (tok/s)",
            ),
            ("Peak concurrent requests", "Peak concurrent requests"),
            ("Total token throughput (tok/s)", "Total token throughput (tok/s)"),
            ("Mean TTFT (ms)", "Mean TTFT (ms)"),
            ("Median TTFT (ms)", "Median TTFT (ms)"),
            ("P95 TTFT (ms)", "P95 TTFT (ms)"),
            ("P99 TTFT (ms)", "P99 TTFT (ms)"),
            ("Mean TPOT (ms)", "Mean TPOT (ms)"),
            ("Median TPOT (ms)", "Median TPOT (ms)"),
            ("P95 TPOT (ms)", "P95 TPOT (ms)"),
            ("P99 TPOT (ms)", "P99 TPOT (ms)"),
            ("Mean ITL (ms)", "Mean ITL (ms)"),
            ("Median ITL (ms)", "Median ITL (ms)"),
            ("P95 ITL (ms)", "P95 ITL (ms)"),
            ("P99 ITL (ms)", "P99 ITL (ms)"),
        ]

    lines = []
    for display_name, key in metric_keys:
        value = metrics.get(key, "N/A")
        lines.append(f"{display_name}:                                 {value}")

    return "\n".join(lines)


def generate_md_report(
    infra,
    chip_name,
    model_name,
    test_suite,
    round_count,
    env,
    serve,
    pd,
    base_path,
    base_url,
    output_file,
    dataset_type="random",
    subset=None,
):
    if dataset_type == "speed_bench":
        concurrencies, num_prompts_list = get_all_concurrencies_speed_bench(base_path)
        if not concurrencies:
            print(f"No concurrency configurations found!")
            return

        first_num_prompts = num_prompts_list[0] if num_prompts_list else "200"
        if not num_prompts_list:
            num_prompts_list = ["200"]
    else:
        concurrencies = get_all_concurrencies(base_path, "01")
        if not concurrencies:
            print(f"No concurrency configurations found!")
            return
        num_prompts_list = None

    round_ids = [f"r{i}" for i in range(1, round_count + 1)]

    title_suffix = build_title_suffix(serve)
    if dataset_type == "speed_bench":
        title = f"# {model_name}-{infra}-{pd}-{subset}"
    elif title_suffix:
        title = f"# {model_name}-{infra}-{pd}-{title_suffix}"
    else:
        title = f"# {model_name}-{infra}-{pd}"

    md_lines = []
    md_lines.append(title)

    md_lines.append("")
    md_lines.append("## Env")
    for env_line in env.strip().split("\n"):
        md_lines.append(f"- {env_line}")

    md_lines.append("")
    md_lines.append("## Dataset")
    if dataset_type == "speed_bench":
        md_lines.append(f"speed_bench_{subset}")
    else:
        md_lines.append(f"random")

    md_lines.append("")
    md_lines.append("## Script")
    md_lines.append("")
    md_lines.append("### Serve")
    for serve_line in serve.strip().split("\n"):
        md_lines.append(serve_line)

    md_lines.append("")
    md_lines.append("### Bench")
    first_conc = concurrencies[0] if concurrencies else "10"
    bench_cmd = generate_benchmark_command(
        infra,
        model_name,
        "${MODEL_PATH}",
        test_suite,
        first_conc,
        base_url,
        dataset_type=dataset_type,
        subset=subset,
    )
    for cmd_line in bench_cmd.strip().split("\n"):
        md_lines.append(cmd_line)

    total_rounds = max(round_count, 3)

    if dataset_type == "speed_bench":
        prompts_list = num_prompts_list or ["200"]
        for conc in concurrencies:
            md_lines.append("")
            md_lines.append(f"## C{conc}")
            md_lines.append("")

            for i in range(total_rounds):
                md_lines.append(f"### R{i + 1}")

                if i < round_count:
                    run_id = f"{i + 1:02d}"
                    for num_prompts in prompts_list:
                        metrics = get_chip_metrics_speed_bench(
                            base_path, run_id, conc, num_prompts, infra
                        )
                        if metrics and (
                            metrics.get("Backend") or metrics.get("Successful requests")
                        ):
                            formatted = format_metrics_for_md(metrics, infra)
                            md_lines.append(formatted)
                        else:
                            md_lines.append("pass")
                else:
                    md_lines.append("pass")

                md_lines.append("")
    else:
        for conc in concurrencies:
            md_lines.append("")
            md_lines.append(f"## C{conc}")
            md_lines.append("")

            for i in range(total_rounds):
                md_lines.append(f"### R{i + 1}")

                if i < round_count:
                    run_id = f"{i + 1:02d}"
                    metrics = get_chip_metrics(base_path, run_id, conc, infra)
                    if metrics and (
                        metrics.get("Backend") or metrics.get("Successful requests")
                    ):
                        formatted = format_metrics_for_md(metrics, infra)
                        md_lines.append(formatted)
                    else:
                        md_lines.append("pass")
                else:
                    md_lines.append("pass")

                md_lines.append("")

    md_content = "\n".join(md_lines)

    with open(output_file, "w", encoding="utf-8") as f:
        f.write(md_content)

    print(f"Generated: {output_file}")
    return output_file


def main():
    parser = argparse.ArgumentParser(
        description="Generate benchmark upload markdown report"
    )
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
        help="Chip name (e.g., nvidia-h100, hygon_bw1000)",
    )
    parser.add_argument("--model", type=str, required=True, help="Model name")
    parser.add_argument(
        "--test-suite",
        type=str,
        default="test_01",
        help="Test suite name (default: test_01)",
    )
    parser.add_argument(
        "--round",
        type=int,
        default=3,
        help="Number of test rounds (default: 3)",
    )
    parser.add_argument(
        "--tester",
        type=str,
        required=True,
        help="Tester name (from Jenkinsfile TESTER parameter)",
    )
    parser.add_argument(
        "--env",
        type=str,
        default=None,
        help="Environment information (from Jenkinsfile ENV parameter)",
    )
    parser.add_argument(
        "--env-file",
        type=str,
        default=None,
        help="File path containing environment information",
    )
    parser.add_argument(
        "--serve",
        type=str,
        default=None,
        help="Serve command (from Jenkinsfile SERVE parameter)",
    )
    parser.add_argument(
        "--serve-file",
        type=str,
        default=None,
        help="File path containing serve command",
    )
    parser.add_argument(
        "--pd",
        type=str,
        required=True,
        choices=["agg", "disagg"],
        help="PD separation mode (from Jenkinsfile PD parameter)",
    )
    parser.add_argument(
        "--base-url",
        type=str,
        required=True,
        help="Base URL for benchmark (from Jenkinsfile BASE_URL parameter)",
    )
    parser.add_argument(
        "--builds-dir",
        type=str,
        required=True,
        help="Builds directory path (e.g., builds/123)",
    )
    parser.add_argument(
        "--build-number",
        type=str,
        default=None,
        help="Jenkins build number for locating reports with build isolation",
    )
    parser.add_argument(
        "--reports-dir",
        type=str,
        default=None,
        help="Reports directory path (default: same as builds-dir)",
    )
    parser.add_argument(
        "--output",
        type=str,
        default=None,
        help="Output markdown file path (default: <builds-dir>/benchmark_upload.md)",
    )
    parser.add_argument(
        "--dataset-type",
        type=str,
        default="random",
        choices=["random", "speed_bench"],
        help="Dataset type (default: random)",
    )
    parser.add_argument(
        "--subset",
        type=str,
        default=None,
        help="Speed bench subset (e.g., 1k, 2k, 8k, 16k, 32k) - required when dataset-type is speed_bench",
    )

    args = parser.parse_args()

    if args.env_file:
        with open(args.env_file, "r", encoding="utf-8") as f:
            env_value = f.read().strip()
    elif args.env:
        env_value = args.env
    else:
        print("Error: --env or --env-file is required")
        return

    if args.serve_file:
        with open(args.serve_file, "r", encoding="utf-8") as f:
            serve_value = f.read().strip()
    elif args.serve:
        serve_value = args.serve
    else:
        print("Error: --serve or --serve-file is required")
        return

    reports_dir = args.reports_dir if args.reports_dir else args.builds_dir
    dataset_type = args.dataset_type.lower()

    if dataset_type == "speed_bench":
        subset = args.subset
        if not subset:
            print("Error: --subset is required when dataset-type is speed_bench")
            return
        if args.tester and args.build_number:
            base_path = f"{reports_dir}/reports-speed_bench/{args.tester}/build-{args.build_number}/{args.infra}/benchmark/{args.chip}/{args.model}/throughput_{subset}"
        elif args.tester:
            base_path = f"{reports_dir}/reports-speed_bench/{args.tester}/{args.infra}/benchmark/{args.chip}/{args.model}/throughput_{subset}"
        elif args.build_number:
            base_path = f"{reports_dir}/reports-speed_bench/build-{args.build_number}/{args.infra}/benchmark/{args.chip}/{args.model}/throughput_{subset}"
        else:
            base_path = f"{reports_dir}/reports-speed_bench/{args.infra}/benchmark/{args.chip}/{args.model}/throughput_{subset}"
    else:
        if args.tester and args.build_number:
            base_path = f"{reports_dir}/reports/{args.tester}/build-{args.build_number}/{args.infra}/benchmark/{args.chip}/{args.model}/{args.test_suite}"
        elif args.tester:
            base_path = f"{reports_dir}/reports/{args.tester}/{args.infra}/benchmark/{args.chip}/{args.model}/{args.test_suite}"
        elif args.build_number:
            base_path = f"{reports_dir}/reports/build-{args.build_number}/{args.infra}/benchmark/{args.chip}/{args.model}/{args.test_suite}"
        else:
            base_path = f"{reports_dir}/reports/{args.infra}/benchmark/{args.chip}/{args.model}/{args.test_suite}"

    output_file = args.output
    if output_file is None:
        curdate = datetime.now().strftime("%Y-%m-%d")
        title_suffix = build_title_suffix(serve_value)
        if dataset_type == "speed_bench":
            file_name = f"{args.model}-{args.infra}-{args.pd}-{args.subset}.md"
        elif title_suffix:
            file_name = f"{args.model}-{args.infra}-{args.pd}-{title_suffix}.md"
        else:
            file_name = f"{args.model}-{args.infra}-{args.pd}.md"

        if dataset_type == "speed_bench":
            dashboard_dir = f"dashboard/{args.tester}/{args.infra}/{args.chip}/{args.model}/speed_bench/{args.subset}/{curdate}"
        else:
            dashboard_dir = f"dashboard/{args.tester}/{args.infra}/{args.chip}/{args.model}/{args.test_suite}/{curdate}"
        Path(dashboard_dir).mkdir(parents=True, exist_ok=True)
        output_file = f"{dashboard_dir}/{file_name}"

    print(f"\n{'=' * 60}")
    print(f"Generate Markdown Report Configuration")
    print(f"{'=' * 60}")
    print(f"Infra: {args.infra}")
    print(f"Chip: {args.chip}")
    print(f"Model: {args.model}")
    print(f"Test Suite: {args.test_suite}")
    print(f"Rounds: {args.round}")
    print(f"Tester: {args.tester}")
    print(f"PD Mode: {args.pd}")
    print(f"Dataset Type: {dataset_type}")
    print(f"Subset: {args.subset}")
    print(f"Base Path: {base_path}")
    print(f"Output File: {output_file}")
    print(f"{'=' * 60}\n")

    generated_file = generate_md_report(
        infra=args.infra,
        chip_name=args.chip,
        model_name=args.model,
        test_suite=args.test_suite,
        round_count=args.round,
        env=env_value,
        serve=serve_value,
        pd=args.pd,
        base_path=base_path,
        base_url=args.base_url,
        output_file=output_file,
        dataset_type=dataset_type,
        subset=args.subset,
    )
    print(f"MARKDOWN_OUTPUT_FILE={generated_file}")


if __name__ == "__main__":
    main()
