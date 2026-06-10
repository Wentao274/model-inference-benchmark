import os
import yaml
import subprocess
import time
from pathlib import Path

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
    dataset_level,
    test_config,
    run_id,
    build_number=None,
    tester=None,
    dataset_path=None,
):
    print(f"Infra: {infra}")
    print(f"Model Name: {served_model_name}")
    print(f"Model Path: {model_path}")
    print(f"Dataset Level: {dataset_level}")

    dataset_levels = test_config.get("dataset-level", [])
    if dataset_level not in dataset_levels:
        print(
            f"Error: dataset-level '{dataset_level}' not in allowed values: {dataset_levels}"
        )
        return

    dataset_name = test_config.get("dataset-name", "speed_bench")
    dataset_path = dataset_path or test_config.get("dataset-path", "")
    output_len = test_config.get("speed-bench-output-len", 1024)
    temperature = test_config.get("temperature", 0.7)
    seed = test_config.get("seed", 123)
    ready_timeout = test_config.get("ready-check-timeout-sec", 30)
    num_prompts_list = test_config.get("num-prompts") or [200]
    max_concurrency_list = test_config.get("max-concurrency") or [10, 30, 60]

    subset = f"throughput_{dataset_level}"
    output_base = f"reports-speed_bench/{infra}/benchmark/{chip_name}/{served_model_name}/{subset}"
    if tester and build_number:
        output_base = f"reports-speed_bench/{tester}/build-{build_number}/{infra}/benchmark/{chip_name}/{served_model_name}/{subset}"
    elif tester:
        output_base = f"reports-speed_bench/{tester}/{infra}/benchmark/{chip_name}/{served_model_name}/{subset}"
    elif build_number:
        output_base = f"reports-speed_bench/build-{build_number}/{infra}/benchmark/{chip_name}/{served_model_name}/{subset}"

    if infra == "vllm":
        for nc in max_concurrency_list:
            for np in num_prompts_list:
                param_dir = f"{run_id}/c{nc}-n{np}"
                output_dir = os.path.join(output_base, param_dir)
                Path(output_dir).mkdir(parents=True, exist_ok=True)

                log_file = os.path.join(
                    output_dir,
                    f"bench-{subset}-c{nc}-n{np}.log",
                )

                cmd = [
                    "vllm",
                    "bench",
                    "serve",
                    "--backend",
                    "openai-chat",
                    "--endpoint",
                    "/v1/chat/completions",
                    "--dataset-name",
                    dataset_name,
                    "--speed-bench-dataset-subset",
                    subset,
                    "--dataset-path",
                    dataset_path,
                    "--model",
                    str(model_path),
                    "--trust-remote-code",
                    "--base-url",
                    base_url,
                    "--num-prompts",
                    str(np),
                    "--max-concurrency",
                    str(nc),
                    "--speed-bench-output-len",
                    str(output_len),
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
    else:
        raise ValueError(f"Only vllm infra is supported, got: {infra}")


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Run speed_bench inference benchmark")
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
        "--dataset-level",
        type=str,
        required=True,
        help="Dataset level (e.g., 1k, 2k, 8k, 16k, 32k)",
    )
    parser.add_argument(
        "--run-id",
        type=str,
        default=RUN_ID,
        help=f"Run ID to identify this test run (default: {RUN_ID})",
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
    parser.add_argument(
        "--dataset-path",
        type=str,
        default=None,
        help="Speed bench dataset path (falls back to config file if not provided)",
    )
    args = parser.parse_args()

    config_path = os.path.join(
        os.path.dirname(__file__), "config", "test_suites_speed_bench.yaml"
    )

    test_config = load_test_suites(config_path)

    run_benchmark(
        infra=args.infra,
        chip_name=args.chip,
        base_url=args.base_url,
        served_model_name=args.model,
        model_path=args.model_path,
        dataset_level=args.dataset_level,
        test_config=test_config,
        run_id=args.run_id,
        build_number=args.build_number,
        tester=args.tester,
        dataset_path=args.dataset_path,
    )


if __name__ == "__main__":
    main()
