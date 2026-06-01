#!/usr/bin/env python3
import os
import sys
import re
import glob
import json
import argparse
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional
import urllib.request
import urllib.error

DEFAULT_BASE_URL = "http://10.220.70.30:18080"


def parse_markdown_for_api(md_path: str) -> Dict[str, Any]:
    with open(md_path, "r", encoding="utf-8") as f:
        content = f.read()

    lines = content.split("\n")

    result = {
        "model_name": "",
        "deployment_name": "",
        "framework": "",
        "pd_mode": "",
        "cache_backend": "NoCache",
        "hardware": "H100",
        "tp_size": None,
        "pp_size": None,
        "ep_size": None,
        "total_gpus": None,
        "deployment_script": "",
        "benchmark_script": "",
        "runs": [],
    }

    current_section = None
    serve_lines = []
    bench_lines = []
    current_concurrency = None
    current_run_no = None

    for i, line in enumerate(lines):
        stripped = line.strip()

        if stripped.startswith("# "):
            result["deployment_name"] = stripped.lstrip("# ").strip()

            match = re.match(r"^(.+?)-(.+?)-(.+?)-?(.*)$", result["deployment_name"])
            if match:
                result["model_name"] = match.group(1)
                result["framework"] = match.group(2)
                result["pd_mode"] = match.group(3)

        elif stripped.startswith("## "):
            section = stripped.lstrip("## ").strip()
            current_section = section

            if section == "Env":
                pass
            elif section == "Script":
                pass
            elif section.startswith("C"):
                match = re.match(r"^C(\d+)$", section)
                if match:
                    current_concurrency = int(match.group(1))

        elif stripped.startswith("### "):
            subsection = stripped.lstrip("### ").strip()

            if subsection == "Serve":
                current_section = "Serve"
            elif subsection == "Bench":
                current_section = "Bench"
            else:
                match = re.match(r"^R(\d+)$", subsection)
                if match:
                    current_run_no = int(match.group(1))
                    current_section = "Run"

        elif stripped == "pass":
            current_run_no = None
            current_concurrency = None

        elif current_section == "Serve" and stripped:
            if not stripped.startswith("#"):
                serve_lines.append(stripped)

        elif current_section == "Bench" and stripped:
            if not stripped.startswith("#"):
                bench_lines.append(stripped)

        elif current_section == "Run" and stripped:
            if ":" in stripped:
                key, value = stripped.split(":", 1)
                key = key.strip()
                value = value.strip()

                if key == "Backend":
                    if result["runs"] and current_run_no is not None:
                        last_run = result["runs"][-1]
                        if (
                            last_run.get("run_no") == current_run_no
                            and last_run.get("concurrency") == current_concurrency
                        ):
                            pass
                        else:
                            result["runs"].append(
                                {
                                    "max_concurrency": current_concurrency,
                                    "run_no": current_run_no,
                                }
                            )
                    else:
                        result["runs"].append(
                            {
                                "max_concurrency": current_concurrency,
                                "run_no": current_run_no,
                            }
                        )

                    result["framework"] = value.lower()

                elif result["runs"]:
                    current_run = result["runs"][-1]
                    if key == "Successful requests":
                        current_run["successful_requests"] = (
                            int(float(value)) if value != "N/A" else None
                        )
                    elif key == "Request throughput (req/s)":
                        current_run["request_qps"] = (
                            float(value) if value != "N/A" else None
                        )
                    elif key == "Input token throughput (tok/s)":
                        current_run["in_qps"] = float(value) if value != "N/A" else None
                    elif key == "Output token throughput (tok/s)":
                        current_run["out_qps"] = (
                            float(value) if value != "N/A" else None
                        )
                    elif key == "Total token throughput (tok/s)":
                        current_run["total_qps"] = (
                            float(value) if value != "N/A" else None
                        )
                    elif key == "Mean TTFT (ms)":
                        current_run["ttft_ms"] = (
                            float(value) if value != "N/A" else None
                        )
                    elif key == "Mean E2E Latency (ms)":
                        current_run["ttot_ms"] = (
                            float(value) if value != "N/A" else None
                        )
                    elif key == "Mean TPOT (ms)":
                        current_run["tpot_ms"] = (
                            float(value) if value != "N/A" else None
                        )
                    elif key == "Mean ITL (ms)":
                        current_run["itl_ms"] = float(value) if value != "N/A" else None
                    elif key == "Peak concurrent requests":
                        current_run["peak_concurrent_requests"] = (
                            float(value) if value != "N/A" else None
                        )

    result["deployment_script"] = "\n".join(serve_lines)
    result["benchmark_script"] = "\n".join(bench_lines)

    if result["deployment_name"]:
        tp_match = re.search(r"tp(\d+)", result["deployment_name"], re.IGNORECASE)
        pp_match = re.search(r"pp(\d+)", result["deployment_name"], re.IGNORECASE)
        ep_match = re.search(r"ep(\d+)", result["deployment_name"], re.IGNORECASE)

        if tp_match:
            result["tp_size"] = int(tp_match.group(1))
        if pp_match:
            result["pp_size"] = int(pp_match.group(1))
        if ep_match:
            result["ep_size"] = int(ep_match.group(1))

        if result["tp_size"] and result["pp_size"] and result["ep_size"]:
            result["total_gpus"] = (
                result["tp_size"] * result["pp_size"] * result["ep_size"]
            )
        elif result["tp_size"]:
            result["total_gpus"] = result["tp_size"]

    if "hicache" in result["deployment_name"].lower():
        result["cache_backend"] = "HiCache-Mem"
    elif "lmcache" in result["deployment_name"].lower():
        if "dingofs" in result["deployment_name"].lower():
            result["cache_backend"] = "LmCache-DingoFS"
        else:
            result["cache_backend"] = "LmCache-Mem"

    valid_runs = [r for r in result["runs"] if "in_qps" in r or "request_qps" in r]
    result["runs"] = valid_runs
    result["run_count"] = len(valid_runs)

    return result


def _build_multipart_body(fields, files):
    boundary = "----PythonFormBoundary7MA4YWxkTrZu0gW"
    body = b""

    for name, value in fields:
        body += f"--{boundary}\r\n".encode()
        body += f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode()
        body += f"{value}\r\n".encode()

    for name, filename, content in files:
        body += f"--{boundary}\r\n".encode()
        body += f'Content-Disposition: form-data; name="{name}"; filename="{filename}"\r\n'.encode()
        body += b"Content-Type: text/markdown\r\n\r\n"
        body += content + b"\r\n"

    body += f"--{boundary}--\r\n".encode()

    return body, boundary


def preview_and_import(
    md_files: List[str],
    base_url: str,
    tester: str,
    test_date: str,
    cache_backend: Optional[str] = None,
    dry_run: bool = False,
) -> bool:
    preview_url = f"{base_url}/api/preview"

    fields = [
        ("tester", tester),
        ("test_date", test_date),
    ]
    if cache_backend:
        fields.append(("cache_backend", cache_backend))

    files_data = []
    for md_file in md_files:
        if os.path.isfile(md_file):
            with open(md_file, "rb") as f:
                content = f.read()
            filename = os.path.basename(md_file)
            files_data.append(("files", filename, content))

    print(f"\n=== 调用预览接口: {preview_url} ===")
    print(f"测试人员: {tester}")
    print(f"测试日期: {test_date}")
    print(f"文件数量: {len(md_files)}")

    try:
        body, boundary = _build_multipart_body(fields, files_data)

        req = urllib.request.Request(
            preview_url,
            data=body,
            headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
            method="POST",
        )

        with urllib.request.urlopen(req, timeout=60) as response:
            response_body = response.read().decode("utf-8")

        print(f"响应状态: 200")

        preview_result = json.loads(response_body)

        print(f"\n预览结果:")
        print(f"  成功解析文件数: {len(preview_result.get('files', []))}")
        print(f"  错误文件数: {len(preview_result.get('errors', []))}")

        for error in preview_result.get("errors", []):
            print(f"  - 文件错误: {error}")

        if not preview_result.get("files"):
            print("错误: 没有成功解析的文件")
            return False

        for file_info in preview_result["files"]:
            runs = file_info.get("runs", [])
            print(f"\n文件: {file_info.get('deployment_name', 'unknown')}")
            print(f"  Version: {file_info.get('version', 'N/A')}")
            print(f"  Run Count: {len(runs)}")
            print(f"  Runs:")
            for run in runs:
                print(
                    f"    - C{run.get('max_concurrency')} R{run.get('run_no')}: "
                    f"in_qps={run.get('in_qps')}, out_qps={run.get('out_qps')}, "
                    f"ttft_ms={run.get('ttft_ms')}, ttot_ms={run.get('ttot_ms')}"
                )

        if dry_run:
            print("\n=== Dry Run 模式，不执行入库 ===")
            return True

        import_url = f"{base_url}/api/import"
        print(f"\n=== 调用入库接口: {import_url} ===")

        import_data = {
            "tester": tester,
            "test_date": test_date,
            "files": preview_result["files"],
        }

        import_body = json.dumps(import_data).encode("utf-8")
        import_req = urllib.request.Request(
            import_url,
            data=import_body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        with urllib.request.urlopen(import_req, timeout=60) as import_response:
            import_result_str = import_response.read().decode("utf-8")

        import_result = json.loads(import_result_str)
        print(f"入库成功!")
        print(f"  插入行数: {import_result.get('inserted_rows', 0)}")
        print(f"  IDs: {import_result.get('ids', [])}")
        return True

    except urllib.error.HTTPError as e:
        error_body = e.read().decode("utf-8") if e.fp else ""
        print(f"HTTP错误: {e.code} {e.reason}")
        print(f"响应内容: {error_body}")
        return False
    except Exception as e:
        print(f"请求出错: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(
        description="Preview and import benchmark markdown files to LLM Benchmark Result Service"
    )
    parser.add_argument("--tester", type=str, required=True, help="Tester name")
    parser.add_argument(
        "--test-date", type=str, required=True, help="Test date in YYYY-MM-DD format"
    )
    parser.add_argument(
        "--md-files",
        type=str,
        nargs="+",
        help="Markdown files to import (default: finds all .md in dashboard/**/*)",
    )
    parser.add_argument(
        "--dashboard-dir",
        type=str,
        default="dashboard",
        help="Dashboard directory to search for markdown files (default: dashboard)",
    )
    parser.add_argument(
        "--cache-backend",
        type=str,
        choices=["NoCache", "LmCache-Mem", "LmCache-DingoFS", "HiCache-Mem"],
        help="Cache backend (optional, auto-detect if not specified)",
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Preview only, do not import"
    )

    args = parser.parse_args()

    if args.md_files:
        md_files = args.md_files
    else:
        md_files = glob.glob(f"{args.dashboard_dir}/**/*.md", recursive=True)

    if not md_files:
        print(f"错误: 找不到 markdown 文件 (搜索目录: {args.dashboard_dir})")
        return 1

    print(f"找到 {len(md_files)} 个 markdown 文件:")
    for f in md_files:
        print(f"  - {f}")

    success = preview_and_import(
        md_files=md_files,
        base_url=DEFAULT_BASE_URL,
        tester=args.tester,
        test_date=args.test_date,
        cache_backend=args.cache_backend,
        dry_run=args.dry_run,
    )

    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
