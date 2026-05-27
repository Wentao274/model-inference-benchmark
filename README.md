# model-inference-benchmark

Performance test of model inference

## run_benchmark.py

通用推理基准测试脚本，支持 vLLM 和 SGLang 两种推理框架。

### 参数说明

| 参数 | 必填 | 说明 |
|------|------|------|
| `--infra` | 是 | 推理框架：`vllm` 或 `sglang` |
| `--base-url` | 是 | 基准测试服务器地址 |
| `--chip` | 是 | 芯片名称（如：`nvidia_h100`, `hygon_bw1000`） |
| `--model` | 是 | served-model-name，模型服务名称 |
| `--model-path` | 是 | 模型路径 |
| `--test-suite` | 否 | 测试套件，默认：`test_01` |
| `--run-id` | 否 | 运行标识符，默认：`01` |

### 使用示例

**vLLM 基准测试：**

```bash
python run_benchmark.py \
  --infra vllm \
  --base-url http://localhost:8080 \
  --chip nvidia_h100 \
  --model Llama-2-7b \
  --model-path /models/Llama-2-7b
```

**SGLang 基准测试：**

```bash
python run_benchmark.py \
  --infra sglang \
  --base-url http://localhost:8000 \
  --chip nvidia_h100 \
  --model Llama-2-7b \
  --model-path /models/Llama-2-7b
```

**指定测试套件：**

```bash
python run_benchmark.py \
  --infra vllm \
  --base-url http://localhost:8080 \
  --chip nvidia_h100 \
  --model Llama-2-7b \
  --model-path /models/Llama-2-7b \
  --test-suite test_02
```

### 配置文件

测试参数在 `config/test_suites.yaml` 中配置，包括：

- `suites`: 测试套件定义（`test_01`, `test_02` 等）
  - `dataset-name`: 数据集名称
  - `max-concurrency`: 并发数列表
  - `num-prompts`: 提示词数量
  - `random-input-output-len`: 输入输出长度配置
- `temperature`: 采样温度
- `seed`: 随机种子
- `random-range-ratio`: 随机范围比例
- `ready-check-timeout-sec`: 就绪检查超时时间

## generate_report.py

基准测试报告生成脚本，支持单次运行报告生成和多次运行对比报告。

### 参数说明

| 参数 | 必填 | 说明 |
|------|------|------|
| `--infra` | 是 | 推理框架：`vllm` 或 `sglang` |
| `--chip` | 是 | 芯片名称（如：`nvidia_h100`, `hygon_bw1000`） |
| `--model` | 是 | 模型名称 |
| `--test-suite` | 否 | 测试套件，默认：`test_01` |
| `--run-id` | 否 | 指定运行 ID，不指定则自动使用最新的 |
| `--compare-with` | 否 | 指定对比的运行 ID，支持逗号分隔多个（如：`run1,run2`），需与 `--run-id` 配合使用 |

### 功能特性

- **单次报告**：当只有 1 个 run-id 时，生成单次测试性能报告
- **对比报告**：当有多个 run-id 时，自动与上一个 run-id 进行对比
  - 自动选择策略：当前 run-id 与最近的上一 run-id 对比
  - 手动指定：使用 `--run-id` 和 `--compare-with` 参数指定基准和对比目标
- **多 Run-ID 对比**：支持3个及以上 run-id 同时对比，所有对比均以 `--run-id` 为基准
- **图表差异标注**：
  - 2个 run-id 对比：折线图显示箭头和差异百分比
  - 3个及以上 run-id 对比：每条对比线都显示箭头和差异百分比
  - 箭头颜色与对应 run-id 的图例颜色一致
  - 百分比标注以 `--run-id` 为基准计算
  - 数值和百分比位置优化，避免重叠
- **报告包含 Benchmark 命令**：报告底部自动生成可执行的 benchmark 命令

### 使用示例

**生成单次报告（只有一个 run-id）：**

```bash
python generate_report.py \
  --infra vllm \
  --chip nvidia_h100 \
  --model Llama-2-7b \
  --test-suite test_01
```

**自动对比（自动选择最近的 run-id 进行对比）：**

```bash
python generate_report.py \
  --infra vllm \
  --chip nvidia_h100 \
  --model Llama-2-7b \
  --test-suite test_01
```

**手动指定 run-id 和对比基准（2个 run-id 对比）：**

```bash
python generate_report.py \
  --infra vllm \
  --chip nvidia_h100 \
  --model Llama-2-7b \
  --test-suite test_01 \
  --run-id 1P1D \
  --compare-with 1P1D+HC
```

**多 run-id 对比（3个及以上）：**

```bash
python generate_report.py \
  --infra vllm \
  --chip kunlun_p800 \
  --model minimax-m2.5 \
  --test-suite test_01 \
  --run-id 1P1D \
  --compare-with 1P1D+HC,1P2D
```

### 输出说明

**测试结果目录结构：**

```
reports/
├── vllm/
│   └── benchmark/
│       └── {chip}/
│           └── {model}/
│               └── {test_suite}/
│                   └── {run_id}/
│                       └── {conc}-{num_prompts}-i{input_len}-o{output_len}/
│                           └── *.log
└── sglang/
    └── benchmark/
        └── {chip}/
            └── {model}/
                └── {test_suite}/
                    └── {run_id}/
                        └── {conc}-{num_prompts}-i{input_len}-o{output_len}/
                            └── *.log
```

**分析报告目录结构：**

```
analysis/
├── vllm/
│   └── {chip}/
│       └── {model}/
│           └── {test_suite}/
│               ├── {run_id}/
│               │   ├── performance_trends.csv
│               │   ├── performance_trends.png
│               │   └── {model}_{chip}_report.md
│               └── compare_{run_id}_{compare_with}/
│                   ├── runid_comparison.csv
│                   ├── runid_comparison.png
│                   └── {model}_{chip}_runid_compare_{run_id}_{compare_with}.md
└── sglang/
    └── ...
```

**单次报告输出（`{run_id}/` 目录）：**

- `performance_trends.csv`: 性能指标 CSV 数据
- `performance_trends.png`: 性能趋势图表
- `{model}_{chip}_report.md`: Markdown 格式单次报告

**对比报告输出（`compare_{run_id}_{compare_with}/` 目录）：**

- `runid_comparison.csv`: Run-ID 对比数据 CSV
- `runid_comparison.png`: Run-ID 对比图表（含差异百分比标注）
- `{model}_{chip}_runid_compare_{run_id}_{compare_with}.md`: Markdown 格式对比报告

**对比报告图表特性：**

- 数据点标注实际数值：
  - 2 个 run-id：基准 run-id 数值在上方，对比 run-id 数值在下方
  - 3 个及以上：第一个在上方，第二个在下方，后续交替放置
- 差异百分比标注：
  - 箭头从基准 run-id 指向对比 run-id，颜色与对应 run-id 一致
  - 百分比标签带边框，更清晰易读
- 支持 2 个或更多 run-id 的对比

**对比报告表格特性（多 run-id）：**

- 表头显示：`RUN-{基准} | RUN-{run_id1} (vs {基准}) | RUN-{run_id2} (vs {基准}) | ...`
- 每行显示：指标名称 | 基准值 | {值} ({百分比}) | ...
- 分析总结部分列出各对比 run-id 相比基准的平均变化，每行之间有换行分隔

**报告底部 Benchmark 命令：**

- 单次报告和对比报告底部都以代码块形式显示对应的 benchmark 执行命令
- 根据 `--infra` 参数自动生成 vLLM 或 SGLang 的命令
- 使用 test-suite 第一个配置的参数值