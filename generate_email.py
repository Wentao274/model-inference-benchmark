import os
import sys
import re
import base64
import json
import zipfile
import argparse


def md_to_html(content):
    lines = content.split("\n")
    result = []
    in_table = False
    table_rows = []

    for line in lines:
        stripped = line.strip()
        if stripped.startswith("|") and stripped.endswith("|"):
            cols = [c.strip() for c in stripped.strip("|").split("|")]
            if all(c in ("---", "") or not any(c) for c in cols):
                continue
            table_rows.append(cols)
            in_table = True
        else:
            if in_table and table_rows:
                result.append(_render_table(table_rows))
                table_rows = []
                in_table = False
            result.append(line)

    if in_table and table_rows:
        result.append(_render_table(table_rows))

    text = "\n".join(result)

    out_parts = []
    pos = 0
    while pos < len(text):
        fence_start = text.find("```", pos)
        if fence_start == -1:
            out_parts.append(_render_inline(text[pos:]))
            break
        out_parts.append(_render_inline(text[pos:fence_start]))
        fence_end = text.find("```", fence_start + 3)
        if fence_end == -1:
            out_parts.append(_render_inline(text[fence_start:]))
            break
        code_content = text[fence_start + 3 : fence_end]
        out_parts.append(
            '<pre style="background:#f4f4f4;border:1px solid #ddd;'
            "border-radius:4px;padding:12px;overflow-x:auto;margin:10px 0;"
            "font-family:monospace;font-size:13px;white-space:pre-wrap;"
            'word-break:break-all;"><code>' + code_content + "</code></pre>"
        )
        pos = fence_end + 3

    return "".join(out_parts)


def _render_inline(text):
    lines = text.split("\n")
    rendered = []
    for ln in lines:
        ln = re.sub(r"^#{3}\s+(.+)$", r"<h4>\1</h4>", ln)
        ln = re.sub(r"^#{2}\s+(.+)$", r"<h3>\1</h3>", ln)
        ln = re.sub(r"^#\s+(.+)$", r"<h2>\1</h2>", ln)
        ln = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", ln)
        ln = re.sub(r"\*(.+?)\*", r"<em>\1</em>", ln)
        rendered.append(ln)
    return "\n".join(rendered)


def _render_table(rows):
    if not rows:
        return ""
    html = ['<table style="border-collapse:collapse;width:100%;margin:10px 0;">']
    for i, row in enumerate(rows):
        tag = "th" if i == 0 else "td"
        style = "background:#f2f2f2;font-weight:bold;" if i == 0 else ""
        html.append("<tr>")
        for cell in row:
            html.append(
                f'<{tag} style="border:1px solid #ddd;padding:8px;{style}">{cell}</{tag}>'
            )
        html.append("</tr>")
    html.append("</table>")
    return "\n".join(html)


def render_report_content(md_path):
    with open(md_path, "r", encoding="utf-8") as mf:
        raw = mf.read()

    md_dir = os.path.dirname(md_path)
    img_pattern = re.compile(r"!\[([^\]]*)\]\(([^)]+\.png)\)")
    for alt_text, img_name in img_pattern.findall(raw):
        img_path = os.path.join(md_dir, img_name)
        if os.path.isfile(img_path):
            with open(img_path, "rb") as imgf:
                img_data = base64.b64encode(imgf.read()).decode("utf-8")
            img_tag = (
                "<br/><img src='data:image/png;base64," + img_data + "' "
                "alt='" + alt_text + "' style='max-width:100%;height:auto;"
                "border:1px solid #ddd;margin:10px 0;'/><br/>"
            )
            raw = raw.replace("![" + alt_text + "](" + img_name + ")", img_tag)

    html = md_to_html(raw)
    return html


def main():
    parser = argparse.ArgumentParser(
        description="Generate email content from benchmark reports"
    )
    parser.add_argument("--builds-dir", required=True)
    parser.add_argument("--engine", required=True)
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
        compare_ids = [c.strip() for c in compare_with.split(",")]
        baseline_id = compare_ids[0]
        comparison_ids = (
            [run_id] + compare_ids[1:] if len(compare_ids) > 1 else [run_id]
        )
        compare_str = "_".join(comparison_ids)
        analysis_dir = os.path.join(
            builds_dir,
            "analysis",
            args.engine,
            args.chip,
            args.model,
            args.test_suite,
            f"compare_{baseline_id}_{compare_str}",
        )
    else:
        analysis_dir = os.path.join(
            builds_dir,
            "analysis",
            args.engine,
            args.chip,
            args.model,
            args.test_suite,
            run_id,
        )

    report_count = 0
    report_html = ""

    if os.path.isdir(analysis_dir):
        for root, dirs, files in os.walk(analysis_dir):
            for fname in sorted(files):
                if fname.endswith(".md"):
                    fpath = os.path.join(root, fname)
                    fname_title = (
                        fname.replace(".md", "").replace("_", " ").replace("-", " ")
                    )
                    try:
                        content_html = render_report_content(fpath)
                        report_html += (
                            '<div class="report-block">'
                            '<h3 style="margin-top:0;color:#2196F3;border-bottom:1px solid #ddd;padding-bottom:10px;">'
                            + fname_title
                            + "</h3>"
                            '<div class="report-content">' + content_html + "</div>"
                            "</div>"
                        )
                        report_count += 1
                        print(f"Processed: {fname}", file=sys.stderr)
                    except Exception as e:
                        print(f"Error: {fpath}: {e}", file=sys.stderr)

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

    output_dir = os.path.dirname(args.output_json)
    os.makedirs(output_dir, exist_ok=True)

    with open(os.path.join(output_dir, "report_count.txt"), "w", encoding="utf-8") as f:
        f.write(str(report_count))
    with open(os.path.join(output_dir, "report_html.txt"), "w", encoding="utf-8") as f:
        f.write(report_html)
    with open(
        os.path.join(output_dir, "log_file_names.txt"), "w", encoding="utf-8"
    ) as f:
        f.write(log_file_names)
    with open(os.path.join(output_dir, "test_status.txt"), "w", encoding="utf-8") as f:
        f.write(test_status)

    print(f"Report count: {report_count}", file=sys.stderr)
    print(f"Done. Files written to: {output_dir}", file=sys.stderr)


if __name__ == "__main__":
    main()
