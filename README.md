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