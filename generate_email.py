import os
import sys
import re
import base64
import json
import zipfile
import argparse


def process_markdown(md_path):
    with open(md_path, "r", encoding="utf-8") as f:
        content = f.read()

    html_content = content
    img_pattern = re.compile(r"!\[([^\]]*)\]\(([^)]+\.png)\)")
    img_matches = img_pattern.findall(content)

    md_dir = os.path.dirname(md_path)
    for alt_text, img_name in img_matches:
        img_path = os.path.join(md_dir, img_name)
        if os.path.isfile(img_path):
            with open(img_path, "rb") as imgf:
                img_data = base64.b64encode(imgf.read()).decode("utf-8")
            img_tag = (
                "<br/><img src='data:image/png;base64," + img_data + "' "
                "alt='" + alt_text + "' style='max-width:100%;height:auto;"
                "border:1px solid #ddd;margin:10px 0;'/><br/>"
            )
            md_img_ref = "![" + alt_text + "](" + img_name + ")"
            html_content = html_content.replace(md_img_ref, img_tag)

    html_content = (
        html_content.replace("\\", "\\\\").replace("\n", "<br/>").replace("\r", "")
    )
    return html_content


def main():
    parser = argparse.ArgumentParser(
        description="Generate email content from benchmark reports"
    )
    parser.add_argument("--builds-dir", required=True)
    parser.add_argument("--infra", required=True)
    parser.add_argument("--chip", required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--test-suite", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--compare-with", default="")
    parser.add_argument("--build-number", type=int, required=True)
    parser.add_argument("--output-json", default="/tmp/email_data.json")
    parser.add_argument("--output-zip", default="/tmp/benchmark_reports.zip")
    args = parser.parse_args()

    builds_dir = args.builds_dir
    run_id = args.run_id
    compare_with = args.compare_with

    if compare_with:
        compare_str = compare_with.replace(",", "_").strip("_")
        analysis_dir = os.path.join(
            builds_dir,
            "analysis",
            args.infra,
            args.chip,
            args.model,
            args.test_suite,
            f"compare_{run_id}_{compare_str}",
        )
    else:
        analysis_dir = os.path.join(
            builds_dir,
            "analysis",
            args.infra,
            args.chip,
            args.model,
            args.test_suite,
            run_id,
        )

    report_blocks = []
    report_count = 0

    if os.path.isdir(analysis_dir):
        for root, dirs, files in os.walk(analysis_dir):
            for fname in sorted(files):
                if fname.endswith(".md"):
                    fpath = os.path.join(root, fname)
                    fname_title = (
                        fname.replace(".md", "").replace("_", " ").replace("-", " ")
                    )
                    try:
                        html_content = process_markdown(fpath)
                        report_blocks.append(
                            {"title": fname_title, "content": html_content}
                        )
                        report_count += 1
                        print(f"Processed: {fname}", file=sys.stderr)
                    except Exception as e:
                        print(f"Error reading {fpath}: {e}", file=sys.stderr)

        with zipfile.ZipFile(args.output_zip, "w", zipfile.ZIP_DEFLATED) as zf:
            for root, dirs, files in os.walk(analysis_dir):
                for fname in files:
                    if fname.endswith((".md", ".png", ".csv")):
                        fpath = os.path.join(root, fname)
                        arcname = os.path.relpath(fpath, builds_dir)
                        zf.write(fpath, arcname)
        print(f"ZIP created: {args.output_zip}", file=sys.stderr)

    log_files = []
    reports_dir = os.path.join(builds_dir, "reports")
    if os.path.isdir(reports_dir):
        for root, dirs, files in os.walk(reports_dir):
            for fname in files:
                if fname.endswith(".log"):
                    log_files.append(fname)

    if log_files:
        log_file_names = "<h4>测试日志文件 (" + str(len(log_files)) + " 个):</h4><ul>"
        for lf in sorted(log_files):
            log_file_names += "<li>" + lf + "</li>"
        log_file_names += "</ul>"
    else:
        log_file_names = "<p>无日志文件</p>"

    test_status = "成功" if report_count > 0 else "失败/无结果"

    result = {
        "report_count": report_count,
        "report_blocks": report_blocks,
        "log_file_names": log_file_names,
        "test_status": test_status,
    }

    with open(args.output_json, "w", encoding="utf-8") as out:
        json.dump(result, out, ensure_ascii=False, indent=2)

    print(f"Report count: {report_count}", file=sys.stderr)
    print(f"Done. JSON: {args.output_json}", file=sys.stderr)


if __name__ == "__main__":
    main()
