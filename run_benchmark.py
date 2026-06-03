import os
import yaml
import subprocess
import time
from itertools import product
from pathlib import Path

API_KEY = os.environ.get("API_KEY", "abc123")

RUN_ID = "01"


def load_test_suites(config_path):
    with open(config_path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)
    return config["test-config"]


def run_benchmark(
    infra,
    chip_name,
    base_url,
    served_model_name,
    model_path,
    test_suites,
    run_id,
    test_config,
    random_range_ratio=None,
    build_number=None,
    tester=None,
):
    print(f"Infra: {infra}")
    print(f"Model Name: {served_model_name}")
    print(f"Model Path: {model_path}")
    print(f"Running test suites: {', '.join(test_suites)}")

    temperature = test_config.get("temperature", 0.7)
    seed = test_config.get("seed", 123)
    ready_timeout = test_config.get("ready-check-timeout-sec", 30)
    if random_range_ratio is None:
        random_range_ratio = test_config.get("random-range-ratio", 0.3)

    output_base = f"reports/{infra}/benchmark/{chip_name}/{served_model_name}"
    if tester and build_number:
        output_base = f"reports/{tester}/build-{build_number}/{infra}/benchmark/{chip_name}/{served_model_name}"
    elif tester:
        output_base = (
            f"reports/{tester}/{infra}/benchmark/{chip_name}/{served_model_name}"
        )
    elif build_number:
        output_base = f"reports/build-{build_number}/{infra}/benchmark/{chip_name}/{served_model_name}"

    params_config = test_config.get("suites", {})

    for test_suite in test_suites:
        test_params = params_config.get(test_suite) or {}
        max_concurrency = test_params.get("max-concurrency", [10])
        num_prompts = test_params.get("num-prompts", [300])
        random_input_output_len = test_params.get(
            "random-input-output-len", [[20000, 100]]
        )

        run_id_dir = os.path.join(output_base, test_suite, run_id)
        if os.path.exists(run_id_dir):
            print(
                f"Error: Run ID '{run_id}' already exists for test suite '{test_suite}' at path: {run_id_dir}"
            )
            print(f"Please either:")
            print(f"  1. Use a different RUN_ID (--run-id)")
            print(f"  2. Delete the existing directory: {run_id_dir}")
            continue

        print(f"\n=== Running test suite: {test_suite} ===")

        for nc, np, io_len in product(
            max_concurrency, num_prompts, random_input_output_len
        ):
            ni = io_len[0]
            no = io_len[1]
            param_dir = f"{test_suite}/{run_id}/{nc}-{np}-i{ni}-o{no}"
            output_dir = os.path.join(output_base, param_dir)
            Path(output_dir).mkdir(parents=True, exist_ok=True)

            log_file = os.path.join(
                output_dir, f"bench-{test_suite}-{nc}-{np}-i{ni}-o{no}.log"
            )

            if infra == "vllm":
                cmd = [
                    "vllm",
                    "bench",
                    "serve",
                    "--backend",
                    "openai-chat",
                    "--endpoint",
                    "/v1/chat/completions",
                    "--dataset-name",
                    test_params.get("dataset-name", "random"),
                    "--random-input-len",
                    str(ni),
                    "--random-output-len",
                    str(no),
                    "--random-range-ratio",
                    str(random_range_ratio),
                    "--model",
                    str(model_path),
                    "--trust-remote-code",
                    "--base-url",
                    base_url,
                    "--num-prompts",
                    str(np),
                    "--max-concurrency",
                    str(nc),
                    "--temperature",
                    str(temperature),
                    "--seed",
                    str(seed),
                    "--metric_percentiles",
                    "95,99",
                    "--served-model-name",
                    str(served_model_name),
                    "--ready-check-timeout-sec",
                    str(ready_timeout),
                ]
            elif infra == "sglang":
                cmd = [
                    "python3",
                    "-m",
                    "sglang.bench_serving",
                    "--backend",
                    "sglang-oai-chat",
                    "--base-url",
                    base_url,
                    "--dataset-name",
                    test_params.get("dataset-name", "random-ids"),
                    "--random-range-ratio",
                    str(random_range_ratio),
                    "--served-model-name",
                    str(served_model_name),
                    "--random-input-len",
                    str(ni),
                    "--random-output-len",
                    str(no),
                    "--max-concurrency",
                    str(nc),
                    "--num-prompt",
                    str(np),
                    "--seed",
                    str(seed),
                ]
                if model_path:
                    cmd.extend(["--model", model_path])
                output_file = os.path.join(
                    output_dir, f"bench-{test_suite}-{nc}-{np}-i{ni}-o{no}.jsonl"
                )
                cmd.extend(["--output-file", output_file])
            else:
                raise ValueError(f"Unknown infra: {infra}")

            print(f"Running: {' '.join(cmd)}")
            print(f"Log file: {log_file}")

            log_f = open(log_file, "w")
            process = subprocess.Popen(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True
            )

            for line in process.stdout:
                print(line, end="")
                log_f.write(line)

            process.wait()
            log_f.close()

            print(f"Completed: {log_file}")
            time.sleep(60)


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Run inference benchmark")
    parser.add_argument(
        "--infra",
        type=str,
        required=True,
        choices=["vllm", "sglang"],
        help="Infrastructure: vllm or sglang",
    )
    parser.add_argument(
        "--base-url", type=str, required=True, help="Base URL for the benchmark server"
    )
    parser.add_argument(
        "--chip",
        type=str,
        required=True,
        help="Chip name to test (e.g., nvidia_h100, hygon_bw1000)",
    )
    parser.add_argument("--model", type=str, required=True, help="Served model name")
    parser.add_argument("--model-path", type=str, required=True, help="Model path")
    parser.add_argument(
        "--test-suite",
        type=str,
        default="test_01",
        help="Test suite to run (default: test_01)",
    )
    parser.add_argument(
        "--run-id",
        type=str,
        default=RUN_ID,
        help=f"Run ID to identify this test run (default: {RUN_ID})",
    )
    parser.add_argument(
        "--random-range-ratio",
        type=float,
        default=None,
        help="Random range ratio for benchmark (default: use value from config file, 0.3)",
    )
    parser.add_argument(
        "--build-number",
        type=str,
        default=None,
        help="Jenkins build number for isolating test results",
    )
    parser.add_argument(
        "--tester",
        type=str,
        default=None,
        help="Tester name for isolating test results",
    )
    args = parser.parse_args()

    config_path = os.path.join(os.path.dirname(__file__), "config", "test_suites.yaml")

    test_config = load_test_suites(config_path)
    params_config = test_config.get("suites", {})

    test_suites_to_run = []
    if args.test_suite:
        test_suites_to_run = [s.strip() for s in args.test_suite.split(",")]
    else:
        test_suites_to_run = ["test_01"]

    invalid_suites = [s for s in test_suites_to_run if s not in params_config]
    if invalid_suites:
        print(
            f"Error: Test suite(s) {invalid_suites} not found in config. Available: {', '.join(params_config.keys())}"
        )
        return

    run_benchmark(
        infra=args.infra,
        chip_name=args.chip,
        base_url=args.base_url,
        served_model_name=args.model,
        model_path=args.model_path,
        test_suites=test_suites_to_run,
        run_id=args.run_id,
        test_config=test_config,
        random_range_ratio=args.random_range_ratio,
        build_number=args.build_number,
        tester=args.tester,
    )


if __name__ == "__main__":
    main()
