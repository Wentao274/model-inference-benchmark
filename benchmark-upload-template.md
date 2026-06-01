# glm-51-sglang-agg-tp8pp2ep8-template

> 使用方式：
> 1. 标题请按部署组合命名，建议格式：glm-51-sglang-agg-tp8pp2ep8-自定义说明。
> 2. agg 表示非 PD 分离，disagg 表示 PD 分离；tp/pp/ep 数字会自动解析。
> 3. Env、Script、C并发、R轮次这些标题不要改名。
> 4. 每个并发下可以保留多轮 R1/R2/R3，未成功的轮次可以写 pass，系统会自动忽略无 Backend 指标的轮次。
> 5. 上传页填写的“手工测试日期”和“是否有缓存”会参与生成最终版本名。

## Env
- GLM-5.1-FP8
- 2 nodes, 8x NVIDIA H100 80GB HBM3 per node (16 GPUs total)
- sglang v0.5.12

## Script

### Serve
sglang serve \
  --model-path /userdata/llms/ZhipuAI/GLM-5.1-FP8 \
  --served-model-name glm-5.1 \
  --trust-remote-code \
  --host 0.0.0.0 --port 8000 \
  --nnodes ${LWS_GROUP_SIZE} \
  --node-rank ${LWS_WORKER_INDEX} \
  --dist-init-addr ${LWS_LEADER_ADDRESS}:29500 \
  --tp-size 8 --pp-size 2 \
  --ep-size 8 \
  --mem-fraction-static 0.85 \
  --kv-cache-dtype fp8_e4m3 \
  --max-running-requests 64 \
  --chunked-prefill-size 16384 \
  --enable-hierarchical-cache \
  --hicache-size 150 \
  --enable-metrics

### Bench
for concurrency in 10 30; do
  for run in 1 2 3; do
    python -m sglang.bench_serving \
      --backend sglang-oai-chat \
      --base-url http://127.0.0.1:8080 \
      --model /userdata/llms/ZhipuAI/GLM-5.1-FP8 \
      --served-model-name glm-5.1 \
      --dataset-name random-ids \
      --random-input-len 50000 \
      --random-output-len 200 \
      --num-prompts 100 \
      --max-concurrency ${concurrency} \
      --seed 123
  done
done

## C10

### R1
Backend:                                 sglang-oai-chat
Traffic request rate:                    inf
Max request concurrency:                 10
Successful requests:                     100
Benchmark duration (s):                  64.08
Request throughput (req/s):              1.56
Input token throughput (tok/s):          34035.13
Output token throughput (tok/s):         168.32
Peak output token throughput (tok/s):    295.00
Peak concurrent requests:                13
Total token throughput (tok/s):          34203.45
Concurrency:                             9.38
Mean E2E Latency (ms):                   6010.74
Median E2E Latency (ms):                 5940.15
P90 E2E Latency (ms):                    9986.53
P99 E2E Latency (ms):                    12213.81
Mean TTFT (ms):                          405.60
Median TTFT (ms):                        387.35
P99 TTFT (ms):                           803.38
Mean TPOT (ms):                          52.29
Median TPOT (ms):                        52.98
P99 TPOT (ms):                           70.51
Mean ITL (ms):                           52.55
Median ITL (ms):                         32.76
P95 ITL (ms):                            170.80
P99 ITL (ms):                            347.03
Max ITL (ms):                            610.43

### R2
pass

### R3
pass

## C30

### R1
Backend:                                 sglang-oai-chat
Traffic request rate:                    inf
Max request concurrency:                 30
Successful requests:                     100
Benchmark duration (s):                  35.80
Request throughput (req/s):              2.79
Input token throughput (tok/s):          60919.03
Output token throughput (tok/s):         301.28
Peak output token throughput (tok/s):    590.00
Peak concurrent requests:                35
Total token throughput (tok/s):          61220.30
Concurrency:                             27.06
Mean E2E Latency (ms):                   9686.90
Median E2E Latency (ms):                 9503.31
P90 E2E Latency (ms):                    17349.41
P99 E2E Latency (ms):                    20904.40
Mean TTFT (ms):                          782.40
Median TTFT (ms):                        451.70
P99 TTFT (ms):                           2060.03
Mean TPOT (ms):                          86.12
Median TPOT (ms):                        86.86
P99 TPOT (ms):                           146.18
Mean ITL (ms):                           83.55
Median ITL (ms):                         42.10
P95 ITL (ms):                            346.73
P99 ITL (ms):                            504.27
Max ITL (ms):                            947.88

### R2
pass

### R3
pass
