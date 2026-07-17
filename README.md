# model-inference-benchmark

模型推理性能基准测试工具，支持 **vLLM** 和 **SGLang** 两种推理框架，提供 `random`（随机数据集）与 `speed_bench`（Speed Bench 数据集）两种测试模式。可通过命令行手动执行，也可通过 Jenkins 流水线自动化执行（远端 Docker 容器内压测 + 报告生成 + 邮件通知 + 结果入库）。

## 目录

- [项目结构](#项目结构)
- [环境准备](#环境准备)
- [配置文件](#配置文件)
- [手动执行测试](#手动执行测试)
  - [run_benchmark.py（random 数据集）](#run_benchmarkpy-random-数据集)
  - [run_benchmark_speed_bench.py（speed_bench 数据集）](#run_benchmark_speed_benchpy-speed_bench-数据集)
- [Jenkins 流水线](#jenkins-流水线)
- [报告生成与入库](#报告生成与入库)
- [输出目录结构](#输出目录结构)

## 项目结构

```
model-inference-benchmark/
├── Jenkinsfile                      # 主流水线（random + speed_bench，带连通性预检）
├── Jenkinsfile_random               # 精简流水线（仅 random，无连通性预检）
├── run_benchmark.py                 # random 数据集基准测试脚本
├── run_benchmark_speed_bench.py     # speed_bench 数据集基准测试脚本
├── generate_md.py                   # 生成 Dashboard 上传用 Markdown 报告
├── generate_report.py               # 生成本地分析报告（含图表、单次/对比）
├── generate_email.py                # 生成邮件内容
├── import_benchmark.py              # 将 Markdown 报告解析并入库到 Dashboard 服务
├── config/
│   ├── test_suites.yaml             # random 数据集测试套件配置
│   └── test_suites_speed_bench.yaml # speed_bench 数据集配置
├── requirements.txt                 # Python 依赖
├── benchmark-upload-template.md     # Markdown 上传模板
└── API.md                           # Dashboard 结果服务接口文档
```

## 环境准备

### 1. Python 依赖

测试脚本依赖 `PyYAML`、`matplotlib`、`pandas`，执行前安装：

```bash
pip install -r requirements.txt
```

### 2. Docker 镜像（Jenkins 流水线使用）

Jenkins 流水线在远端主机的 Docker 容器内执行压测，需提前准备对应推理框架的镜像：

| 推理框架 | 镜像 |
|----------|------|
| vLLM | `vllm/vllm-openai:v0.21.0-cu129` |
| SGLang | `lmsysorg/sglang:v0.5.12` |

容器启动参数（见 `Jenkinsfile`）：

```bash
docker run -d --name <容器名> \
    --network host \
    --memory=32g \
    --shm-size=1g \
    --entrypoint bash \
    -v <WORK_DIR>:/workspace/bench-dashboard/model-inference-benchmark \
    -v <MODEL_PATH>:<MODEL_PATH> \
    -v /root/.cache/huggingface:/root/.cache/huggingface \
    -w /workspace/bench-dashboard/model-inference-benchmark \
    <镜像> -c "sleep infinity"
```

### 3. 远端主机与 SSH（Jenkins 流水线使用）

主流水线通过 SSH 在远端主机上执行 Docker 命令，相关配置在 `Jenkinsfile` 的 `environment` 中：

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `SSH_CREDENTIALS` | `HOST_SSH_KEY` | Jenkins 存储的 SSH 凭据标识 |
| `REMOTE_HOST` | `10.201.132.50` | 远端压测主机 |
| `REMOTE_USER` | `root` | SSH 登录用户 |
| `WORK_DIR` | `/dingofs/data2/userdata/liwt/maas-image/bench-dashboard/model-inference-benchmark` | 远端仓库工作目录 |

### 4. 模型服务前置条件

执行测试前，**被测模型服务必须已启动**并能通过 OpenAI 兼容接口访问：

- `GET  {BASE_URL}/v1/models` 返回 200
- `POST {BASE_URL}/v1/chat/completions` 可正常响应

> `BASE_URL` 不带 `/v1` 后缀，例如 `http://10.201.149.10:8080`。

主流水线（`Jenkinsfile`）会在测试前执行「API 连通性预检」，若失败则跳过后续压测阶段并将构建置为 `UNSTABLE`。

### 5. 配置文件

测试参数在 `config/` 目录下配置，详见 [配置文件](#配置文件) 章节。

## 配置文件

### test_suites.yaml（random 数据集）

`run_benchmark.py` 读取此文件。顶层 `test-config` 下包含全局参数与 `suites` 套件定义：

```yaml
test-config:
  suites:
    test_01:
      round: 3                              # 建议测试轮数（实际轮数由命令行/Jenkins ROUND 控制）
      dataset-name: random-ids              # 数据集名（注：run_benchmark.py 实际按引擎硬编码，vllm=random, sglang=random-ids）
      max-concurrency: [ 10, 30, 60 ]       # 并发数列表
      num-prompts: [ 100 ]                  # 每个并发下的提示词数量
      random-input-output-len: [ [ 50000, 200 ] ]  # [输入长度, 输出长度] 组合
    test_02:
      round: 3
      dataset-name: random-ids
      max-concurrency: [ 1, 10 ]
      num-prompts: [ 100 ]
      random-input-output-len: [[ 194560, 1024 ]]
  temperature: 0.7                          # 采样温度
  seed: 123                                 # 随机种子
  random-range-ratio: 0.0                   # 随机范围比例（命令行 --random-range-ratio 优先）
  ready-check-timeout-sec: 30               # 服务就绪检查超时（秒）
```

> **关于 `random-range-ratio`**：配置文件中默认值为 `0.0`；若配置文件未设置该项，代码兜底默认值为 `0.3`。命令行 `--random-range-ratio` 优先级最高。

### test_suites_speed_bench.yaml（speed_bench 数据集）

`run_benchmark_speed_bench.py` 读取此文件：

```yaml
test-config:
  dataset-name: speed_bench                                   # 数据集名
  dataset-path: /dingofs/data2/userdata/datasets/speed-bench-without-hle  # 数据集路径
  dataset-level: [ 1k, 2k, 8k, 16k, 32k ]                    # 可选子集
  round: 3
  max-concurrency: [ 10, 30, 60 ]
  num-prompts: [ 100 ]
  speed-bench-output-len: 1024                                # 默认输出长度（可被命令行覆盖）
  temperature: 0.7
  seed: 123
  ready-check-timeout-sec: 30
```

> **注意**：`run_benchmark_speed_bench.py` 当前**仅支持 vLLM 引擎**，传入 `sglang` 会抛出 `ValueError`。

## 手动执行测试

### run_benchmark.py（random 数据集）

通用推理基准测试脚本，支持 vLLM 和 SGLang。

#### 参数说明

| 参数 | 必填 | 说明 |
|------|------|------|
| `--engine` | 是 | 推理引擎：`vllm` 或 `sglang` |
| `--base-url` | 是 | 被测服务地址（不带 `/v1` 后缀） |
| `--chip` | 是 | 芯片名称（如：`nvidia_h100`, `hygon_bw1000`） |
| `--model` | 是 | served-model-name，模型服务名称 |
| `--model-path` | 是 | 模型路径 |
| `--test-suite` | 否 | 测试套件，默认 `test_01`，支持逗号分隔多个 |
| `--run-id` | 否 | 运行标识符，默认 `01`（同一套件下重复会跳过） |
| `--random-range-ratio` | 否 | 随机范围比例，命令行优先于配置文件（配置默认 `0.0`，代码兜底 `0.3`） |
| `--build-number` | 否 | Jenkins 构建号，用于隔离测试结果目录 |
| `--tester` | 否 | 测试人员名，用于隔离测试结果目录 |

> 当 `--tester` 和 `--build-number` 同时提供时，结果输出到 `reports/{tester}/build-{build_number}/...`，用于 Jenkins 流水线隔离多次构建。

#### 使用示例

**vLLM 基准测试：**

```bash
python run_benchmark.py \
  --engine vllm \
  --base-url http://localhost:8080 \
  --chip nvidia_h100 \
  --model Llama-2-7b \
  --model-path /models/Llama-2-7b
```

**SGLang 基准测试：**

```bash
python run_benchmark.py \
  --engine sglang \
  --base-url http://localhost:8000 \
  --chip nvidia_h100 \
  --model Llama-2-7b \
  --model-path /models/Llama-2-7b
```

**指定测试套件与 run-id：**

```bash
python run_benchmark.py \
  --engine vllm \
  --base-url http://localhost:8080 \
  --chip nvidia_h100 \
  --model Llama-2-7b \
  --model-path /models/Llama-2-7b \
  --test-suite test_02 \
  --run-id 02
```

**指定 random-range-ratio（命令行参数优先于配置文件）：**

```bash
python run_benchmark.py \
  --engine vllm \
  --base-url http://localhost:8080 \
  --chip nvidia_h100 \
  --model Llama-2-7b \
  --model-path /models/Llama-2-7b \
  --random-range-ratio 0.5
```

**模拟 Jenkins 隔离输出（带 tester/build-number）：**

```bash
python run_benchmark.py \
  --engine vllm \
  --base-url http://localhost:8080 \
  --chip nvidia-h100 \
  --model kimi-k2.5 \
  --model-path /models/Kimi-K2.6 \
  --test-suite test_01 \
  --run-id 01 \
  --tester liwt \
  --build-number 123 \
  --random-range-ratio 0.0
```

#### 执行逻辑

1. 加载 `config/test_suites.yaml`，校验 `--test-suite` 是否存在
2. 对每个套件，按 `max-concurrency × num-prompts × random-input-output-len` 笛卡尔积遍历参数组合
3. 若 `run_id` 目录已存在则跳过该套件并提示
4. 每个组合调用 `vllm bench serve`（vllm）或 `python3 -m sglang.bench_serving`（sglang）执行压测，日志写入对应目录
5. 每个组合执行完后等待 60 秒再进入下一个

### run_benchmark_speed_bench.py（speed_bench 数据集）

基于 Speed Bench 数据集的吞吐基准测试脚本，**仅支持 vLLM 引擎**。

#### 参数说明

| 参数 | 必填 | 说明 |
|------|------|------|
| `--engine` | 是 | 推理引擎（当前仅 `vllm` 实际可用） |
| `--base-url` | 是 | 被测服务地址（不带 `/v1` 后缀） |
| `--chip` | 是 | 芯片名称 |
| `--model` | 是 | served-model-name |
| `--model-path` | 是 | 模型路径 |
| `--dataset-level` | 是 | 数据集子集：`1k` / `2k` / `8k` / `16k` / `32k` |
| `--run-id` | 否 | 运行标识符，默认 `01` |
| `--build-number` | 否 | Jenkins 构建号，用于隔离结果目录 |
| `--tester` | 否 | 测试人员名，用于隔离结果目录 |
| `--dataset-path` | 否 | Speed Bench 数据集路径，未指定则读配置文件 |
| `--speed-bench-output-len` | 否 | 输出长度，留空则不指定该参数（使用配置默认 1024） |

#### 使用示例

```bash
python run_benchmark_speed_bench.py \
  --engine vllm \
  --base-url http://localhost:8080 \
  --chip nvidia-h100 \
  --model kimi-k2.5 \
  --model-path /models/Kimi-K2.6 \
  --dataset-level 8k
```

**指定输出长度与数据集路径：**

```bash
python run_benchmark_speed_bench.py \
  --engine vllm \
  --base-url http://localhost:8080 \
  --chip nvidia-h100 \
  --model kimi-k2.5 \
  --model-path /models/Kimi-K2.6 \
  --dataset-level 8k \
  --dataset-path /data/speed-bench-without-hle \
  --speed-bench-output-len 2048
```

#### 执行逻辑

1. 加载 `config/test_suites_speed_bench.yaml`，校验 `--dataset-level` 是否在允许列表内
2. 子集映射为 `throughput_{level}`（如 `throughput_8k`）
3. 按 `max-concurrency × num-prompts` 笛卡尔积遍历，调用 `vllm bench serve` 并传入 `--speed-bench-dataset-subset`
4. 结果写入 `reports-speed_bench/...` 目录，每个组合执行完后等待 60 秒

## Jenkins 流水线

仓库提供两个 Jenkinsfile：

| 文件 | 适用场景 | 数据集 | 连通性预检 | Agent |
|------|----------|--------|-----------|-------|
| `Jenkinsfile` | **主流水线（推荐）** | `random` + `speed_bench` | 是 | `slave-3` |
| `Jenkinsfile_random` | 精简流水线（历史） | 仅 `random` | 否 | `any` |

### 执行模型

两个流水线均采用「Jenkins Master → SSH 远端主机 → Docker 容器内执行」的模型：

1. Jenkins 通过 `sshagent`（凭据 `HOST_SSH_KEY`）登录远端主机 `10.201.132.50`
2. 在远端启动 Docker 容器（vllm/sglang 镜像），挂载 `WORK_DIR`、模型路径与 HuggingFace 缓存
3. 容器内安装 `requirements.txt` 依赖后，执行 `run_benchmark.py` / `run_benchmark_speed_bench.py`
4. 多轮测试（`ROUND` 参数）依次执行，每轮间隔 60 秒，`run_id` 为 `01`、`02`、…（两位补零）
5. 测试结果与报告通过 `scp` 拉回 Jenkins workspace 并归档为 artifact

### Jenkinsfile（主流水线）参数

| 参数 | 说明 |
|------|------|
| `TESTER` | 测试人员名称（必填） |
| `CHIP` | 芯片平台名称（必填） |
| `ENGINE` | 推理框架：`vllm` / `sglang` |
| `PD` | PD 分离模式：`agg`（非分离）/ `disagg`（PD 分离） |
| `MODEL` | 模型服务名称（必填） |
| `MODEL_PATH` | 模型文件本地路径（host 绝对路径） |
| `BASE_URL` | API 地址（必填，不带 `/v1`） |
| `DATASET_TYPE` | 数据集类型：`random` / `speed_bench` |
| `SUBSET` | Speed Bench 子集：`1k`/`2k`/`8k`/`16k`/`32k`（仅 `speed_bench` 使用） |
| `SPEED_BENCH_DATASET_PATH` | Speed Bench 数据集路径（仅 `speed_bench` 使用） |
| `SPEED_BENCH_OUTPUT_LEN` | Speed Bench 输出长度（留空则不指定） |
| `TEST_SUITE` | 测试套件（仅 `random` 使用）：`test_01` / `test_02` |
| `ROUND` | 测试轮数（执行几轮相同测试） |
| `RANDOM_RANGE_RATIO` | 随机范围比例 |
| `SERVE` | 模型服务部署命令（必填，写入报告） |
| `ENV` | 测试环境信息 JSON（必填，写入报告） |
| `FOR_FACTORY` | 是否为生产模型：`YES` 时入库到生产 Dashboard |
| `DESCRIPTION` | 模型服务的描述信息 |
| `RECIPIENTS` | 测试报告邮件接收者（逗号分隔） |
| `WORK_DIR` | 测试仓库目录（默认值请勿改动） |

### Jenkinsfile 流水线阶段

主流水线（`Jenkinsfile`）按顺序执行以下 stage：

1. **打印测试参数**：输出所有构建参数便于排查
2. **API 连通性预检**：在远端 `curl` 校验 `/v1/models` 与 `/v1/chat/completions`；失败则置 `CONNECTIVITY_FAILED=true`，构建置 `UNSTABLE`，后续压测 stage 跳过
3. **环境检查**（连通性通过才执行）：在远端检查工作目录、Docker、配置文件
4. **启动容器并运行 Benchmark**（连通性通过才执行）：
   - 清理旧容器 → 启动新容器 → 安装依赖
   - 按 `ROUND` 循环执行，`random` 调用 `run_benchmark.py`，`speed_bench` 调用 `run_benchmark_speed_bench.py`
   - 每轮 `run_id` 为 `01`、`02`…，轮间等待 60 秒
   - 该 stage 失败仅置 `UNSTABLE`，不中断后续报告生成
5. **生成 Markdown 报告**：容器内调用 `generate_md.py`，根据 `DATASET_TYPE` 生成 Dashboard 上传用 Markdown，输出文件路径通过 `MARKDOWN_OUTPUT_FILE=` 返回
6. **备份结果到 builds 目录**：将当前构建的 dashboard 文件复制到 `builds/{BUILD_NUMBER}/`
7. **拉取测试结果**：`scp` 将远端 `builds/{BUILD_NUMBER}/` 与 `import_benchmark.py` 拉回 Jenkins workspace，同时拉取连通性预检日志
8. **发送邮件**：用 `emailext` 发送 HTML 邮件，附带 Markdown 报告；连通性失败时附连通性日志并标红
9. **解析并入库**：在 Jenkins 节点调用 `import_benchmark.py`，将当前构建的 Markdown 解析并入库到 Dashboard 服务（`FOR_FACTORY=YES` 时入库到生产地址 `http://10.201.134.28:18080`）
10. **清理容器**：删除远端 Docker 容器
11. **post**：始终归档 `builds/{BUILD_NUMBER}/**` 与连通性日志，最后 `cleanWs()` 清理 workspace

### Jenkinsfile_random（精简流水线）差异

`Jenkinsfile_random` 是早期版本，仅支持 `random` 数据集，与主流水线的主要差异：

- **无连通性预检**：直接进入环境检查与压测
- **无 `DATASET_TYPE` / `SUBSET` / speed_bench 相关参数**：仅测试 `random`
- **无 `FOR_FACTORY` / `DESCRIPTION`**：入库始终使用默认 Dashboard 地址
- **`ENV` 参数为纯文本**（非 JSON），`generate_md.py` 会按行解析
- **备份策略不同**：直接复制整个 dashboard 日期目录，而非按 `build{BUILD_NUMBER}-*.md` 过滤
- **入库过滤不同**：使用所有 dashboard 下的 `.md`，而非过滤当前构建号
- **邮件无连通性失败处理**：不读取连通性日志，无失败原因红色提示框

> 新场景建议使用主流水线 `Jenkinsfile`。

## 报告生成与入库

### generate_md.py

生成 **Dashboard 上传用 Markdown 报告**（Jenkins 流水线 stage 5 调用）。该脚本解析 benchmark 日志，按并发（`## C{N}`）与轮次（`### R{N}`）组织指标，并附上环境信息、Serve/Bench 脚本。

主要参数：

| 参数 | 必填 | 说明 |
|------|------|------|
| `--engine` | 是 | `vllm` / `sglang` |
| `--chip` | 是 | 芯片名 |
| `--model` | 是 | 模型名 |
| `--test-suite` | 否 | 测试套件（默认 `test_01`） |
| `--round` | 否 | 测试轮数（默认 3） |
| `--tester` | 是 | 测试人员（来自 Jenkins `TESTER`） |
| `--env` / `--env-file` | 二选一 | 环境信息（来自 Jenkins `ENV`） |
| `--serve` / `--serve-file` | 二选一 | 部署命令（来自 Jenkins `SERVE`） |
| `--pd` | 是 | `agg` / `disagg` |
| `--base-url` | 是 | 被测服务地址 |
| `--builds-dir` | 是 | builds 输出目录 |
| `--build-number` | 否 | Jenkins 构建号 |
| `--reports-dir` | 否 | 报告根目录（默认同 `--builds-dir`） |
| `--dataset-type` | 否 | `random`（默认）/ `speed_bench` |
| `--subset` | 否 | speed_bench 子集（`speed_bench` 时必填） |

输出文件命名规则（写入 `dashboard/{tester}/{engine}/{chip}/{model}/.../{date}/`）：

- random：`build{N}-{model}-{engine}-{pd}[-{tp}{pp}{ep}].md`
- speed_bench：`build{N}-{model}-{engine}-{pd}-{subset}.md`

脚本会从 `SERVE` 命令中正则解析 `--tp`/`--dp`/`--pp`/`--ep` 并拼入标题后缀；`ENV` 支持 JSON（`{"Env":{...}}`）或纯文本两种格式。

### generate_report.py

生成本地分析报告，支持单次运行报告与多次运行对比报告（含 matplotlib 图表）。报告底部自动生成可执行的 benchmark 命令，参数占位符为 `${MODEL_PATH}` 和 `${BASE_URL}`。

#### 参数说明

| 参数 | 必填 | 说明 |
|------|------|------|
| `--engine` | 是 | 推理引擎：`vllm` 或 `sglang` |
| `--chip` | 是 | 芯片名称 |
| `--model` | 是 | 模型名称 |
| `--test-suite` | 否 | 测试套件，默认 `test_01` |
| `--run-id` | 否 | 指定运行 ID，不指定则自动使用最新的 |
| `--compare-with` | 否 | 对比的运行 ID，逗号分隔多个（如 `run1,run2`），需与 `--run-id` 配合。以 `--compare-with` 的第一个值为基准 |

#### 功能特性

- **单次报告**：当只有 1 个 run-id 时，生成单次测试性能报告
- **对比报告**：使用 `--run-id` 和 `--compare-with` 指定对比
  - **基准选择逻辑**：
    - `--run-id 01 --compare-with 03`：以 `RUN-03` 为基准，`RUN-01` 为对比目标
    - `--run-id 01 --compare-with 03,04`：以 `RUN-03` 为基准，`RUN-01` 和 `RUN-04` 为对比目标
    - 输出目录命名：`compare_{基准}_{对比目标}`，如 `compare_03_01` 或 `compare_03_01_04`
  - 表格显示：`RUN-{基准} | RUN-{对比1} (vs {基准}) | RUN-{对比2} (vs {基准}) | ...`
- **自动对比**（无 `--run-id` 时）：自动选择最近的两个 run-id 进行对比，以较旧的为基准
- **图表差异标注**：
  - 2 个 run-id 对比：折线图显示箭头和差异百分比
  - 3 个及以上 run-id 对比：每条对比线都显示箭头和差异百分比
  - 箭头颜色与对应 run-id 的图例颜色一致，百分比标注以基准 run-id 计算

#### 使用示例

**生成单次报告（只有一个 run-id）：**

```bash
python generate_report.py \
  --engine vllm \
  --chip nvidia_h100 \
  --model Llama-2-7b \
  --test-suite test_01
```

**手动指定 run-id 和对比基准（以 compare-with 为基准）：**

```bash
python generate_report.py \
  --engine vllm \
  --chip nvidia_h100 \
  --model Llama-2-7b \
  --test-suite test_01 \
  --run-id 01 \
  --compare-with 03
```

结果：以 `RUN-03` 为基准，`RUN-01` 为对比，输出目录 `compare_03_01`

**多 run-id 对比（3 个及以上）：**

```bash
python generate_report.py \
  --engine vllm \
  --chip kunlun_p800 \
  --model minimax-m2.5 \
  --test-suite test_01 \
  --run-id 01 \
  --compare-with 03,04
```

结果：以 `RUN-03` 为基准，`RUN-01` 和 `RUN-04` 为对比目标，输出目录 `compare_03_01_04`

### import_benchmark.py

将 `generate_md.py` 产出的 Markdown 报告解析并入库到 Dashboard 结果服务（接口详见 `API.md`）。Jenkins 流水线 stage 9 调用。

主要参数：

| 参数 | 必填 | 说明 |
|------|------|------|
| `--tester` | 是 | 测试人员 |
| `--test-date` | 是 | 测试日期 `YYYY-MM-DD` |
| `--md-files` | 否 | 待入库的 Markdown 文件（未指定则递归搜索 `dashboard/**/*.md`） |
| `--dashboard-dir` | 否 | 搜索目录（默认 `dashboard`） |
| `--cache-backend` | 否 | 缓存后端：`NoCache`/`LmCache-Mem`/`LmCache-DingoFS`/`HiCache-Mem`，留空自动推断 |
| `--base-url` | 否 | Dashboard 服务地址（默认 `http://10.220.75.93:18080`；`FOR_FACTORY=YES` 时由 Jenkins 改为生产地址） |
| `--dry-run` | 否 | 仅预览不入库 |

执行流程：先调用 `POST /api/preview` 解析预览，再调用 `POST /api/import` 写入 SQLite。支持 `--dry-run` 仅预览校验。

## 输出目录结构

### Benchmark 原始日志（random 数据集）

```
reports/
└── {engine}/benchmark/{chip}/{model}/{test_suite}/{run_id}/{conc}-{num_prompts}-i{input_len}-o{output_len}/*.log
```

带 `tester` / `build-number` 隔离时：

```
reports/{tester}/build-{build_number}/{engine}/benchmark/{chip}/{model}/{test_suite}/{run_id}/.../*.log
```

### Benchmark 原始日志（speed_bench 数据集）

```
reports-speed_bench/
└── {engine}/benchmark/{chip}/{model}/throughput_{subset}/{run_id}/c{conc}-n{num_prompts}/*.log
```

带 `tester` / `build-number` 隔离时：

```
reports-speed_bench/{tester}/build-{build_number}/{engine}/benchmark/{chip}/{model}/throughput_{subset}/{run_id}/.../*.log
```

### Dashboard 上传报告（generate_md.py 输出）

```
dashboard/{tester}/{engine}/{chip}/{model}/{test_suite}/{date}/build{N}-{model}-{engine}-{pd}[-{tp}{pp}{ep}].md
dashboard/{tester}/{engine}/{chip}/{model}/speed_bench/{subset}/{date}/build{N}-{model}-{engine}-{pd}-{subset}.md
```

### 本地分析报告（generate_report.py 输出）

```
analysis/
└── {engine}/{chip}/{model}/{test_suite}/
    ├── {run_id}/
    │   ├── performance_trends.csv
    │   ├── performance_trends.png
    │   └── {model}_{chip}_report.md
    └── compare_{基准}_{对比目标}/
        ├── runid_comparison.csv
        ├── runid_comparison.png
        └── {model}_{chip}_runid_compare.md
```

### Jenkins 归档（builds 目录）

```
builds/{BUILD_NUMBER}/dashboard/{tester}/{engine}/{chip}/{model}/.../*.md
builds/connectivity_{BUILD_NUMBER}.log   # 连通性预检日志（仅主流水线）
```
