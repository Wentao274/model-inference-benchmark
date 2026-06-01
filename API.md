# LLM Benchmark Result Service — 接口文档

LLM 推理性能测试结果管理服务的 HTTP 接口说明。服务基于 FastAPI 实现，提供
Markdown 测试结果的解析、入库、筛选、对比曲线等能力。

- 应用入口：`app/main.py`（`app = create_app()`）
- 数据访问层：`app/store.py`（SQLite）
- 解析层：`app/parser.py`（解析 `sglang.bench_serving` 输出的 Markdown）

---

## 1. 部署与访问

### 1.1 部署目标（DHost）

| 项 | 值 |
| --- | --- |
| 主机别名 | `DHost` |
| 远程目录 | `/home/ubuntu/huzx/llm-infer-bench-service`（可用 `REMOTE_DIR` 覆盖） |
| 监听地址 | `0.0.0.0`（脚本默认） |
| 端口 | `18080`（可用 `PORT` 覆盖） |
| 数据库 | `outputs/benchmark-service/benchmarks.sqlite` |
| 日志 | `logs/benchmark-service.log` |
| PID 文件 | `run/benchmark-service.pid` |
| Python 运行环境 | 服务目录下的 `.venv`（启动脚本自动创建） |

访问基址（Base URL）：`http://<DHost-IP>:18080`

### 1.2 一键部署 / 启停

```bash
# 本地推送代码到 DHost 并重启（rsync + 远程 restart）
scripts/deploy_dhost.sh

# 覆盖目标主机 / 目录 / 端口
REMOTE_HOST=DHost REMOTE_DIR=<target-dir> PORT=18080 scripts/deploy_dhost.sh

# 在 DHost 上手动启停
scripts/start_service.sh
scripts/stop_service.sh
scripts/restart_service.sh
```

> 注意：`deploy_dhost.sh` 的 rsync 会 `--delete` 同步，但显式排除了
> `outputs/benchmark-service/benchmarks.sqlite`，因此**部署不会覆盖线上数据库**。

### 1.3 本地运行（开发调试）

```bash
python3 -m pip install -r requirements.txt
python3 -m uvicorn app.main:app --host 127.0.0.1 --port 18080
```

---

## 2. 约定

- **Base URL**：`http://<host>:18080`
- **编码**：请求/响应均为 UTF-8。
- **数据格式**：除文件上传（`multipart/form-data`）和模板下载外，均为 `application/json`。
- **认证**：当前无鉴权（内网服务）。
- **错误返回**：FastAPI 标准错误体 `{"detail": <string | object | array>}`，并携带相应 HTTP 状态码（常见 `400`、`422`）。

### 公共字段：测试结果行（result row）

入库后单条记录（`benchmark_results` 表）的字段。`/api/results` 返回这些字段，
解析预览 `/api/preview` 的 `runs` 是其中的指标子集。

| 字段 | 类型 | 含义 |
| --- | --- | --- |
| `id` | int | 主键 |
| `model_name` | string | 模型名，如 `GLM-5.1` |
| `version` | string | 版本标识（见 §5.1 生成规则），同一部署组合的曲线分组键 |
| `engine_version` | string\|null | 推理框架版本，如 `sglang v0.5.12` |
| `tester` | string | 测试人 |
| `test_date` | string | 测试日期，紧凑格式 `YYYYMMDD` |
| `test_time` | string | 原始日期字符串（`YYYY-MM-DD`） |
| `test_datetime` | string | 测试时间（回填自 `test_time`/`test_date`） |
| `deployment_name` | string | 部署名（来自文件名/标题，无扩展名） |
| `pd_mode` | string | `agg`（非 PD 分离）或 `pd`（PD 分离） |
| `framework` | string | 框架，小写，如 `sglang` / `vllm` |
| `cache_backend` | string | 缓存后端，见 §5.2 |
| `deployment_parallelism` | string | 并行度字符串，如 `tp8pp2ep8` |
| `tp_size` / `pp_size` / `ep_size` | int\|null | 张量/流水线/专家并行度 |
| `hardware` | string | `H100` 或 `H200` |
| `total_gpus` | int\|null | GPU 总数 |
| `deployment_script` | string | 部署/serve 脚本原文 |
| `deployment_params_json` | string(JSON) | 从部署脚本解析出的 CLI 参数 |
| `benchmark_script` | string | bench 脚本原文 |
| `benchmark_params_json` | string(JSON) | 从 bench 脚本解析出的 CLI 参数 |
| `source_file` | string | 来源文件名 |
| `max_concurrency` | int | 并发级别（`## C{N}`） |
| `run_no` | int | 轮次号（`### R{N}`） |
| `request_qps` | real\|null | 请求吞吐 req/s |
| `in_qps` | real | 输入 token 吞吐 tok/s |
| `out_qps` | real | 输出 token 吞吐 tok/s |
| `total_qps` | real | 总 token 吞吐 tok/s（缺失时由 in+out 推算） |
| `qps_per_gpu` | real\|null | `total_qps / total_gpus` |
| `ttft_ms` | real | 平均首 token 延迟（Mean TTFT） |
| `ttot_ms` | real | 平均端到端延迟（Mean E2E Latency） |
| `tpot_ms` | real\|null | 平均每 token 输出时间 |
| `itl_ms` | real\|null | 平均 token 间延迟 |
| `successful_requests` | int\|null | 成功请求数 |
| `benchmark_duration_s` | real\|null | 压测时长 |
| `created_at` | string | 入库时间（`datetime('now')`） |

---

## 3. 页面与静态资源

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| `GET` | `/` | 302 重定向到 `/dashboard` |
| `GET` | `/dashboard` | 测试汇总看板页面（HTML） |
| `GET` | `/upload` | 测试结果上传页面（HTML） |
| `GET` | `/static/*` | 静态资源（`app/static/`，含 `app.js`、`styles.css`、`vendor/echarts.min.js`） |

---

## 4. 接口详情

### 4.1 下载上传模板

获取标准的 Markdown 上传模板（用于填写部署脚本、bench 脚本、各并发各轮次结果）。

```
GET /api/templates/benchmark-markdown
```

- **响应**：`text/markdown; charset=utf-8`，作为附件 `benchmark-upload-template.md` 下载。
- 模板内的标题（`## Env` / `## Script` / `## C{N}` / `### R{N}` 等）**不可改名**，解析器依赖它们。

---

### 4.2 解析预览

上传一个或多个 Markdown 文件，解析为结构化结果但**不入库**，用于上传前预览校验。

```
POST /api/preview
Content-Type: multipart/form-data
```

**表单字段**

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `tester` | string | 是 | 测试人 |
| `test_date` | string | 是 | 手工测试日期，`YYYY-MM-DD` |
| `cache_backend` | string | 否 | 缓存后端，留空则按文件内容自动推断（见 §5.2） |
| `files` | file[] | 是 | 一个或多个 `.md` 文件 |

**成功响应** `200`

```json
{
  "files": [
    {
      "model_name": "GLM-5.1",
      "deployment_name": "glm-51-sglang-agg-tp8pp2ep8-hicache",
      "version": "GLM-5.1-20260528-H100-sglang-agg-HiCache-Mem-8TP2PP8EP",
      "pd_mode": "agg",
      "framework": "sglang",
      "cache_backend": "HiCache-Mem",
      "hardware": "H100",
      "tp_size": 8, "pp_size": 2, "ep_size": 8,
      "total_gpus": 16,
      "tester": "胡宗星",
      "test_date": "2026-05-28",
      "run_count": 6,
      "runs": [
        { "max_concurrency": 10, "run_no": 1, "in_qps": 12345.6, "out_qps": 49.3,
          "total_qps": 12394.9, "qps_per_gpu": 774.7, "ttft_ms": 1234.5, "ttot_ms": 5678.9, "...": "..." }
      ],
      "deployment_script": "sglang serve \\ ...",
      "benchmark_script": "for concurrency in 10 30; do ..."
    }
  ],
  "errors": [
    { "file": "bad.md", "error": "no benchmark runs found" }
  ]
}
```

- `files`：成功解析的文件列表，每项是「公开版」解析结果（含 §2 的元数据字段、`runs` 数组、`run_count`、`version`，以及脚本原文）。
- `errors`：逐文件的解析错误（非 `.md`、解析异常、无有效 run 等）。
- 单个文件可解析但 `runs` 为空（无含 `Backend:` 的指标块）时，该文件计入 `errors`。

**错误响应**

| 状态码 | 场景 |
| --- | --- |
| `400` | 所有文件都解析失败（`detail` 为 errors 数组） |
| `422` | 缺少必填表单字段（FastAPI 校验） |

> 用途：前端拿到 `/api/preview` 的 `files` 后，用户确认无误，再原样作为 `/api/import` 的 `files` 提交入库。

---

### 4.3 确认入库

将预览得到的解析结果写入数据库。

```
POST /api/import
Content-Type: application/json
```

**请求体**

```json
{
  "tester": "胡宗星",
  "test_date": "2026-05-28",
  "files": [ /* 来自 /api/preview 的 files 项，每项需含 version 和非空 runs */ ]
}
```

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `tester` | string | 是 | 测试人 |
| `test_date` | string | 是 | 测试日期 `YYYY-MM-DD` |
| `files` | object[] | 是 | 预览结果数组；每项必须包含 `version` 与非空 `runs` |

**成功响应** `200`

```json
{ "inserted_rows": 18, "ids": [101, 102, 103, "..."] }
```

- `inserted_rows`：写入的明细行数（= 所有文件的 run 数之和，每个 run 一行）。
- `ids`：新插入行的自增主键列表。

**错误响应**

| 状态码 | 场景 |
| --- | --- |
| `400` | `files` 为空，或某文件缺少 `tester`/`test_date`/`version`/`runs` |

> 入库时 `test_date` 会被同时存为紧凑格式（`test_date` = `YYYYMMDD`）和原始格式（`test_time` = `YYYY-MM-DD`）。

---

### 4.4 获取筛选项

返回看板筛选下拉框的可选值（基于库内现有数据 + 预置测试人/缓存项）。

```
GET /api/filters
```

**成功响应** `200`

```json
{
  "models": ["GLM-5.1"],
  "versions": ["GLM-5.1-20260528-H100-sglang-agg-HiCache-Mem-8TP2PP8EP", "..."],
  "test_dates": ["20260528"],
  "hardwares": ["H100", "H200"],
  "frameworks": ["sglang"],
  "pd_modes": ["agg", "pd"],
  "cache_backends": ["HiCache-Mem", "NoCache"],
  "testers": ["丁健珊", "于海军", "胡宗星", "..."],
  "cache_backend_options": ["NoCache", "LmCache-Mem", "LmCache-DingoFS", "HiCache-Mem"]
}
```

- `models`/`versions`/… ：来自库内 `DISTINCT` 值。
- `testers`：库内已有测试人 ∪ 预置测试人名单（共 20 人）。
- `cache_backend_options`：缓存后端固定枚举（上传页下拉用）。

---

### 4.5 查询结果列表

按筛选条件返回明细行（最近优先，最多 500 条）。

```
GET /api/results
```

**Query 参数**（均可选，可重复传同名参数表示多选 `IN`）

| 参数 | 说明 |
| --- | --- |
| `model_name` | 模型名 |
| `version` | 版本标识 |
| `test_date` | 测试日期（`YYYYMMDD`） |
| `hardware` | `H100` / `H200` |
| `framework` | `sglang` / `vllm` |
| `pd_mode` | `agg` / `pd` |
| `cache_backend` | 缓存后端 |
| `tester` | 测试人 |

> 其他参数会被忽略；值为空、`all`、`None` 视为不过滤。多选示例：`?version=A&version=B`。

**成功响应** `200`

```json
{ "rows": [ { /* 一条完整 result row，字段见 §2 */ } ] }
```

- 排序：`created_at DESC, id DESC`；上限 500 行。

---

### 4.6 对比曲线数据

按 `version` 分组、按并发聚合（同并发多轮取**平均值**）的曲线数据，供前端 ECharts 绘制。

```
GET /api/chart?metric=<metric>
```

**Query 参数**

| 参数 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `metric` | string | 否 | 指标名，默认 `total_qps` |
| `ids` | string | 否 | 逗号分隔的行 id（`?ids=1,2,3`），用于只对选中行作图 |
| 其余筛选参数 | — | 否 | 同 §4.5（`model_name`/`version`/`hardware`/… 多选同样支持） |

**支持的 `metric`**：`in_qps`、`out_qps`、`total_qps`、`qps_per_gpu`、`ttft_ms`、`ttot_ms`。
传入其它值返回 `500`（`unsupported metric`）。

**成功响应** `200`

```json
{
  "metric": "total_qps",
  "series": [
    {
      "name": "GLM-5.1-20260528-H100-sglang-agg-HiCache-Mem-8TP2PP8EP",
      "points": [
        { "concurrency": 10, "value": 12394.9, "runs": 3 },
        { "concurrency": 30, "value": 28765.4, "runs": 3 }
      ]
    }
  ]
}
```

- 每条 `series` 对应一个 `version`；`points` 按并发升序。
- `value` = 该 (version, concurrency) 下 `metric` 的平均值；`runs` = 参与平均的样本数。

---

## 5. 解析与版本规则（参考）

### 5.1 版本标识（version）生成

`version` 由元数据拼接而成（`app/parser.py: build_version`）：

```
{model_name}-{YYYYMMDD}-{hardware}-{framework}-{pd_mode}-{cache_backend}-{tp}TP{pp}PP{ep}EP
```

示例：`GLM-5.1-20260528-H100-sglang-agg-HiCache-Mem-8TP2PP8EP`

`version` 是看板曲线的分组键：相同部署组合 + 相同测试日期/缓存 → 同一条曲线。

### 5.2 缓存后端（cache_backend）

固定枚举：`NoCache`、`LmCache-Mem`、`LmCache-DingoFS`、`HiCache-Mem`。

- 上传/预览时未显式指定，则从文件名与正文自动推断：
  含 `hicache`/`hierarchical-cache` → `HiCache-Mem`；含 `lmcache`+`dingofs` → `LmCache-DingoFS`；
  仅含 `lmcache` → `LmCache-Mem`；否则 `NoCache`。

### 5.3 Markdown 解析要点

- `## Env`：解析模型变体、硬件（出现 `NVIDIA H200`/`h200` → `H200`，否则 `H100`）、
  节点数/每节点 GPU 数/总 GPU 数、框架与引擎版本。
- `## Script`：`### Serve`（或 disagg 的 Prefill/Decode）归为部署脚本，`### Bench` 归为 bench 脚本；
  两段脚本都会被解析为 CLI 参数 JSON。
- `## C{N}` → 并发级别；其下 `### R{N}` → 轮次。只有包含 `Backend:` 的指标块才会被收录为一条 run；
  写 `pass` 或缺指标的轮次会被忽略。
- `total_qps` 缺失时由 `in_qps + out_qps` 推算；`qps_per_gpu = total_qps / total_gpus`。

---

## 6. 数据存储

- 引擎：SQLite，文件 `outputs/benchmark-service/benchmarks.sqlite`。
- 表：`benchmark_results`（字段见 §2），每条 run 一行。
- 索引：`version`、`(model_name, test_date, framework, pd_mode, cache_backend)`、`(version, max_concurrency)`。
- 启动时自动建表（`init_db`），幂等。

---

## 7. 接口速查

| 方法 | 路径 | 用途 |
| --- | --- | --- |
| `GET` | `/` | 跳转看板 |
| `GET` | `/dashboard` | 看板页面 |
| `GET` | `/upload` | 上传页面 |
| `GET` | `/static/*` | 静态资源 |
| `GET` | `/api/templates/benchmark-markdown` | 下载上传模板 |
| `POST` | `/api/preview` | 解析预览（不入库） |
| `POST` | `/api/import` | 确认入库 |
| `GET` | `/api/filters` | 筛选项 |
| `GET` | `/api/results` | 查询明细行 |
| `GET` | `/api/chart` | 对比曲线数据 |
