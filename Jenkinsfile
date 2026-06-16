pipeline {
    agent any
    parameters {
        string(name: 'TESTER', defaultValue: 'liwt', description: '测试人员名称')
        choice(name: 'INFRA', choices: ['vllm', 'sglang'], description: '推理框架')
        string(name: 'CHIP', defaultValue: 'nvidia-h100', description: '芯片平台名称')
        choice(name: 'PD', choices: ['agg', 'disagg'], description: 'PD分离模式,agg 表示非 PD 分离, disagg 表示 PD 分离')
        string(name: 'MODEL', defaultValue: 'kimi-k2.5', description: '模型名称（served-model-name）')
        string(name: 'MODEL_PATH', defaultValue: '/dingofs/data1/userdata/llms/moonshotai/Kimi-K2.6', description: '模型文件本地路径 (必填，目前仅支持五区的模型路径，请只修改xxx/llms/后的路径名，前面的不要改动)')
        string(name: 'BASE_URL', defaultValue: 'http://10.201.149.10:8080', description: 'API 地址，注意没有/v1后缀')
        choice(name: 'DATASET_TYPE', choices: ['random', 'speed_bench'], description: '数据集类型')
        choice(name: 'SUBSET', choices: ['1k', '2k', '8k', '16k', '32k'], description: 'Speed Bench子集(仅speed_bench时使用)')
        string(name: 'SPEED_BENCH_DATASET_PATH', defaultValue: '/dingofs/data1/userdata/datasets/speed-bench-without-hle', description: 'Speed Bench数据集路径(仅speed_bench时使用)')
        string(name: 'SPEED_BENCH_OUTPUT_LEN', defaultValue: '', description: 'Speed Bench输出长度(仅供speed_bench数据集测试时使用，留空则不指定该参数)')
        string(name: 'TEST_SUITE', defaultValue: 'test_01', description: '测试套件（仅random数据集使用，可选: test_01, test_02）')
        string(name: 'ROUND', defaultValue: '3', description: '测试轮数（执行几轮相同测试）')
        string(name: 'RANDOM_RANGE_RATIO', defaultValue: '0.0', description: '随机范围比例（random-range-ratio）')
        text(name: 'RECIPIENTS', defaultValue: 'liwt@zetyun.com', description: '邮件接收者（逗号分隔）')
        text(name: 'SERVE', defaultValue: '', description: '模型服务部署命令')
        text(name: 'ENV', defaultValue: '''Kimi-K2.6
2 nodes, 8x NVIDIA H100 80GB HBM3 per node (16 GPUs total)
vllm v0.21.0''', description: '测试环境信息')
        string(name: 'WORK_DIR', defaultValue: '/dingofs/data1/userdata/liwt/maas-image/bench-dashboard/model-inference-benchmark', description: '测试仓库目录，请不要修改')
    }
    environment {
        SSH_CREDENTIALS = 'HOST_SSH_KEY'
        REMOTE_HOST = '10.201.132.50'
        REMOTE_USER = 'root'
        VLLM_IMAGE = 'vllm/vllm-openai:v0.21.0-cu129'
        SGLANG_IMAGE = 'lmsysorg/sglang:v0.5.12'
    }

    stages {
        stage('环境检查') {
            steps {
                sshagent(credentials: ["${SSH_CREDENTIALS}"]) {
                    script {
                        def datasetType = params.DATASET_TYPE.toLowerCase()
                        println("=== 环境检查 ===")
                        sh """
ssh -o StrictHostKeyChecking=no ${REMOTE_USER}@${REMOTE_HOST} << 'ENDSSH'
cd ${params.WORK_DIR}
echo "=== 工作目录 ==="
pwd
ls -la
echo "=== 测试参数信息 ==="
echo "测试人员: ${params.TESTER}"
echo "推理框架: ${params.INFRA}"
echo "数据集类型: ${params.DATASET_TYPE}"
echo "Subset: ${params.SUBSET}"
echo "芯片类型: ${params.CHIP}"
echo "PD分离模式: ${params.PD}"
echo "模型服务名称: ${params.MODEL}"
echo "模型路径: ${params.MODEL_PATH}"
echo "BASE_URL: ${params.BASE_URL}"
echo "测试套件: ${params.TEST_SUITE}"
echo "测试轮数: ${params.ROUND}"
echo "随机范围比例: ${params.RANDOM_RANGE_RATIO}"
echo "服务部署命令: ${params.SERVE}"
echo "BUILD_NUMBER: ${BUILD_NUMBER}"
echo "=== Docker 检查 ==="
docker --version
echo "=== 测试目录结构 ==="
ls -la config/
echo "=== 检查配置文件 ==="
cat config/test_suites.yaml
echo "=== 检查 speed_bench 配置文件 ==="
cat config/test_suites_speed_bench.yaml
ENDSSH
"""
                    }
                }
            }
        }

stage('启动容器并运行 Benchmark') {
            steps {
                script {
                    def infra = params.INFRA.toLowerCase()
                    def datasetType = params.DATASET_TYPE.toLowerCase()
                    def image = infra == 'vllm' ? env.VLLM_IMAGE : env.SGLANG_IMAGE
                    def containerName = "dashboard-model-bench-${params.CHIP}-${params.MODEL}-${BUILD_NUMBER}"
                    def round = params.ROUND.toInteger()
                    def speedBenchDatasetPath = params.SPEED_BENCH_DATASET_PATH
                    env.CONTAINER_NAME = containerName

                    println("=== 启动 ${infra.toUpperCase()} 容器 ===")
                    println("镜像: ${image}")
                    println("容器名: ${containerName}")
                    println("测试轮数: ${round}")
                    println("数据集类型: ${datasetType}")

                    sshagent(credentials: ["${SSH_CREDENTIALS}"]) {
                        catchError(buildResult: 'UNSTABLE', stageResult: 'FAILURE') {
                            sh """
ssh -o StrictHostKeyChecking=no ${REMOTE_USER}@${REMOTE_HOST} << 'ENDSSH'
set -e
echo "=== 清理旧容器 ==="
docker rm -f ${containerName} 2>/dev/null || true

#echo "=== 拉取镜像: ${image} ==="
#docker pull ${image}

echo "=== 启动容器 ==="
docker run -d --name ${containerName} \
    --network host \
    --memory=32g \
    --shm-size=1g \
    --entrypoint bash \
    -v ${params.WORK_DIR}:/workspace/bench-dashboard/model-inference-benchmark \
    -v ${params.MODEL_PATH}:${params.MODEL_PATH} \
    -v /root/.cache/huggingface:/root/.cache/huggingface \
    ${datasetType == 'speed_bench' ? "-v ${speedBenchDatasetPath}:${speedBenchDatasetPath}" : ""} \
    -w /workspace/bench-dashboard/model-inference-benchmark \
    ${image} \
    -c "sleep infinity"

echo "=== 等待容器启动 ==="
sleep 20

echo "=== 容器状态 ==="
docker ps | grep ${containerName}

echo "=== 安装测试依赖 ==="
export https_proxy=http://100.64.1.68:1080
export http_proxy=http://100.64.1.68:1080
docker exec ${containerName} bash -c "cd /workspace/bench-dashboard/model-inference-benchmark && pip install -q -r requirements.txt || pip3 install -q -r requirements.txt"
unset https_proxy
unset http_proxy

echo "=== 检查 Python 命令 ==="
PYTHON_CMD=\$(docker exec ${containerName} bash -c "command -v python3 || command -v python || echo 'python3'")
echo "使用 Python 命令: \${PYTHON_CMD}"
ENDSSH
"""
                            
                            for (int i = 1; i <= round; i++) {
                                def currentRunId = String.format('%02d', i)
                                def bashCmd = ""
                                
                                if (datasetType == 'random') {
                                    bashCmd = """
ssh -o StrictHostKeyChecking=no ${REMOTE_USER}@${REMOTE_HOST} << 'ENDSSH'
echo "=== 执行第 ${i}/${round} 轮测试 (RUN_ID: ${currentRunId}) ==="
echo "数据集类型: random"
PYTHON_CMD=\$(docker exec ${containerName} bash -c "command -v python3 || command -v python || echo 'python3'")
docker exec ${containerName} bash -c \\
    "\${PYTHON_CMD} run_benchmark.py \\
        --infra ${params.INFRA} \\
        --base-url '${params.BASE_URL}' \\
        --chip ${params.CHIP} \\
        --model ${params.MODEL} \\
        --model-path ${params.MODEL_PATH} \\
        --test-suite ${params.TEST_SUITE} \\
        --run-id ${currentRunId} \\
        --build-number ${BUILD_NUMBER} \\
        --tester ${params.TESTER} \\
        --random-range-ratio ${params.RANDOM_RANGE_RATIO}"
echo "=== 第 ${i} 轮测试完成 ==="
ENDSSH
"""
} else if (datasetType == 'speed_bench') {
                                    def outputLenArg = params.SPEED_BENCH_OUTPUT_LEN?.trim() ? "--speed-bench-output-len ${params.SPEED_BENCH_OUTPUT_LEN}" : ""
                                    bashCmd = """
ssh -o StrictHostKeyChecking=no ${REMOTE_USER}@${REMOTE_HOST} << 'ENDSSH'
echo "=== 执行第 ${i}/${round} 轮测试 (RUN_ID: ${currentRunId}) ==="
echo "数据集类型: speed_bench"
echo "Subset: ${params.SUBSET}"
PYTHON_CMD=\$(docker exec ${containerName} bash -c "command -v python3 || command -v python || echo 'python3'")
docker exec ${containerName} bash -c \\
    "\${PYTHON_CMD} run_benchmark_speed_bench.py \\
        --infra ${params.INFRA} \\
        --base-url '${params.BASE_URL}' \\
        --chip ${params.CHIP} \\
        --model ${params.MODEL} \\
        --model-path ${params.MODEL_PATH} \\
        --dataset-level ${params.SUBSET} \
        --dataset-path ${params.SPEED_BENCH_DATASET_PATH} \
        ${outputLenArg} \\
        --run-id ${currentRunId} \\
        --build-number ${BUILD_NUMBER} \\
        --tester ${params.TESTER}"
echo "=== 第 ${i} 轮测试完成 ==="
ENDSSH
"""
                                }
                                sh bashCmd
                                if (i < round) {
                                    println("=== 等待60秒后开始下一轮测试 ===")
                                    sleep(time: 60, unit: 'SECONDS')
                                }
                            }
                            
                            sh """
ssh -o StrictHostKeyChecking=no ${REMOTE_USER}@${REMOTE_HOST} << 'ENDSSH'
echo "=== 所有轮次 Benchmark 执行完成 ==="
#unset https_proxy
#unset http_proxy
#unset no_proxy
ENDSSH
"""
                        }
                    }
                }
            }
        }

stage('生成Markdown报告') {
            steps {
                script {
                    def containerName = env.CONTAINER_NAME
                    def round = params.ROUND.toInteger()
                    def buildsDir = "builds/${BUILD_NUMBER}"
                    def datasetType = params.DATASET_TYPE.toLowerCase()

                    sshagent(credentials: ["${SSH_CREDENTIALS}"]) {
                        catchError(buildResult: 'UNSTABLE', stageResult: 'FAILURE') {
                            def mdOutput = sh(
                                script: """
ssh -o StrictHostKeyChecking=no ${REMOTE_USER}@${REMOTE_HOST} << 'ENDSSH'
set -e
PYTHON_CMD=\$(docker exec ${containerName} bash -c "command -v python3 || command -v python || echo 'python3'")
echo "使用 Python 命令: \${PYTHON_CMD}"

echo "=== 写入参数文件 ==="
cat > /tmp/env_param.txt << 'ENVEOF'
${params.ENV}
ENVEOF

cat > /tmp/serve_param.txt << 'SERVEEOF'
${params.SERVE}
SERVEEOF

docker cp /tmp/env_param.txt ${containerName}:/tmp/env_param.txt
docker cp /tmp/serve_param.txt ${containerName}:/tmp/serve_param.txt

echo "=== 执行 generate_md.py ==="
docker exec ${containerName} bash -c \
    "\${PYTHON_CMD} /workspace/bench-dashboard/model-inference-benchmark/generate_md.py \
        --infra ${params.INFRA} \
        --chip ${params.CHIP} \
        --model ${params.MODEL} \
        --test-suite ${params.TEST_SUITE} \
        --round ${round} \
        --tester ${params.TESTER} \
        --env-file /tmp/env_param.txt \
        --serve-file /tmp/serve_param.txt \
        --pd ${params.PD} \
        --base-url '${params.BASE_URL}' \
        --reports-dir /workspace/bench-dashboard/model-inference-benchmark \
        --build-number ${BUILD_NUMBER} \
        --builds-dir /workspace/bench-dashboard/model-inference-benchmark/${buildsDir} \
        --dataset-type ${datasetType} \
        --subset ${params.SUBSET}" 2>&1 | tee /tmp/md_output.log

grep "MARKDOWN_OUTPUT_FILE=" /tmp/md_output.log | cut -d'=' -f2
ENDSSH
""",
                                returnStdout: true
                            ).trim()
                            env.MD_OUTPUT_FILE = mdOutput
                            println("Markdown输出文件: ${mdOutput}")
                        }
                    }
                }
            }
        }

        stage('备份结果到 builds 目录') {
            steps {
                sshagent(credentials: ["${SSH_CREDENTIALS}"]) {
                    catchError(buildResult: 'UNSTABLE', stageResult: 'FAILURE') {
                        script {
                            def round = params.ROUND.toInteger()
                            def buildsDir = "builds/${BUILD_NUMBER}"
                            def datasetType = params.DATASET_TYPE.toLowerCase()
                            def dashboardSuite = datasetType == 'speed_bench' ? "speed_bench/${params.SUBSET}" : params.TEST_SUITE
                            
                            println("=== 备份测试结果到 ${buildsDir} (共 ${round} 轮) ===")
                            
                            sh """
ssh -o StrictHostKeyChecking=no ${REMOTE_USER}@${REMOTE_HOST} << 'ENDSSH'
set -e
BUILDS_DIR=${params.WORK_DIR}/${buildsDir}

echo "=== 创建 builds 目录结构 ==="
mkdir -p "\${BUILDS_DIR}"
ENDSSH
"""
                            
                            sh """
ssh -o StrictHostKeyChecking=no ${REMOTE_USER}@${REMOTE_HOST} << 'ENDSSH'
set -e
BUILDS_DIR=${params.WORK_DIR}/${buildsDir}
CURDATE=\$(date +%Y-%m-%d)
DASHBOARD_DIR="${params.WORK_DIR}/dashboard/${params.TESTER}/${params.INFRA}/${params.CHIP}/${params.MODEL}/${dashboardSuite}/\${CURDATE}"

echo "=== 复制 dashboard 目录到 builds 目录 ==="
if [ -d "\${DASHBOARD_DIR}" ]; then
    mkdir -p "\${BUILDS_DIR}/dashboard/${params.TESTER}/${params.INFRA}/${params.CHIP}/${params.MODEL}/${dashboardSuite}"
    cp -r "\${DASHBOARD_DIR}" "\${BUILDS_DIR}/dashboard/${params.TESTER}/${params.INFRA}/${params.CHIP}/${params.MODEL}/${dashboardSuite}/"
    echo "dashboard 目录复制完成: \${DASHBOARD_DIR} -> \${BUILDS_DIR}/dashboard/"
else
    echo "警告: dashboard 目录不存在: \${DASHBOARD_DIR}"
fi

echo "=== 备份完成，查看目录结构 ==="
find ${params.WORK_DIR}/${buildsDir} -type d | head -30
ENDSSH
"""
                        }
                    }
                }
            }
        }

stage('拉取测试结果') {
            steps {
                sshagent(credentials: ["${SSH_CREDENTIALS}"]) {
                    catchError(buildResult: 'UNSTABLE', stageResult: 'FAILURE') {
                        script {
                            def buildsDir = "builds/${BUILD_NUMBER}"
                            
                            println("=== 拉取测试结果到 Jenkins workspace ===")
                            
                            sh """
set -e
echo "=== 拉取 builds 目录到 Jenkins workspace ==="
rm -rf ${buildsDir}
mkdir -p builds

scp -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -r ${REMOTE_USER}@${REMOTE_HOST}:${params.WORK_DIR}/${buildsDir}/ ./builds/
scp -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null ${REMOTE_USER}@${REMOTE_HOST}:${params.WORK_DIR}/import_benchmark.py ./import_benchmark.py

echo "=== 拉取完成，查看目录结构 ==="
find ./${buildsDir} -maxdepth 3 -type d
echo "=== 日志文件数量 ==="
find ./${buildsDir} -name '*.log' | wc -l
echo "=== 报告文件数量 ==="
find ./${buildsDir} -name '*.md' | wc -l
"""
                        }
                    }
                }
            }
}

        stage('发送邮件') {
            steps {
                catchError(buildResult: 'UNSTABLE', stageResult: 'FAILURE') {
                    script {
                        def infra = params.INFRA.toUpperCase()
                        def round = params.ROUND.toInteger()
                        def runIdList = (1..round).collect { String.format('%02d', it) }.join(', ')
                        def buildsDir = "builds/${BUILD_NUMBER}"
                        def datasetType = params.DATASET_TYPE.toLowerCase()
                        def datasetInfoRow = datasetType == 'speed_bench' ? "<tr><td>Subset</td><td>${params.SUBSET}</td></tr>" : "<tr><td>测试套件</td><td>${params.TEST_SUITE}</td></tr>"
                        
                        def mdFiles = findFiles(glob: "${buildsDir}/dashboard/**/*.md")
                        def reportHtml = ""
                        def testStatus = "成功"
                        
                        if (mdFiles && mdFiles.length > 0) {
                            for (def mdFile : mdFiles) {
                                def mdContent = readFile(mdFile.path)
                                def escapedContent = mdContent
                                    .replace('&', '&amp;')
                                    .replace('<', '&lt;')
                                    .replace('>', '&gt;')
                                    .replace('\n', '<br/>')
                                reportHtml += """
                                    <div class="report-block">
                                        <h3 style="margin-top:0;color:#2196F3;border-bottom:1px solid #ddd;padding-bottom:10px;">
                                            ${mdFile.name}
                                        </h3>
                                        <div class="report-content"><pre style="background:#f4f4f4;border:1px solid #ddd;border-radius:4px;padding:12px;overflow-x:auto;font-family:monospace;font-size:12px;white-space:pre-wrap;word-break:break-all;">${escapedContent}</pre></div>
                                    </div>
                                """
                            }
                            testStatus = "成功"
                        } else {
                            reportHtml = '<p>无报告文件</p>'
                            testStatus = "失败/无结果"
                        }

                        def emailBody = """
<html>
<head>
    <meta charset="UTF-8">
    <style>
        body { font-family: Arial, sans-serif; margin: 0; padding: 20px; background-color: #f5f5f5; }
        .container { max-width: 1000px; margin: 0 auto; background-color: #fff; border-radius: 5px; box-shadow: 0 2px 5px rgba(0,0,0,0.1); }
        .header { background-color: ${testStatus == '成功' ? '#2196F3' : '#f44336'}; color: white; padding: 20px; border-radius: 5px 5px 0 0; }
        .content { padding: 20px; }
        table { border-collapse: collapse; width: 100%; margin-top: 15px; }
        th, td { border: 1px solid #ddd; padding: 10px; text-align: left; }
        th { background-color: #f2f2f2; }
        h3 { color: #333; border-bottom: 2px solid #2196F3; padding-bottom: 5px; }
        .report-block { margin-bottom: 20px; border: 1px solid #ddd; padding: 15px; background-color: #fafafa; border-radius: 5px; }
        .report-content { font-size: 13px; line-height: 1.5; background-color: #f9f9f9; padding: 15px; border-radius: 3px; max-height: 600px; overflow-y: auto; }
        .report-content pre { background:#f4f4f4;border:1px solid #ddd;border-radius:4px;padding:12px;overflow-x:auto;margin:10px 0;font-family:monospace;font-size:12px;white-space:pre-wrap;word-break:break-all; }
        .report-content code { font-family: monospace; }
    </style>
</head>
<body>
<div class="container">
<div class="header">
    <h2 style="margin: 0;">Model Inference Benchmark 测试报告 - 构建 #${BUILD_NUMBER}</h2>
</div>
<div class="content">
    <h3>测试概要</h3>
    <table>
        <tr><th>项目</th><td>值</td></tr>
        <tr><td>构建编号</td><td>#${BUILD_NUMBER}</td></tr>
        <tr><td>测试人员</td><td>${params.TESTER}</td></tr>
        <tr><td>芯片平台</td><td>${params.CHIP}</td></tr>
        <tr><td>推理框架</td><td>${infra}</td></tr>
        <tr><td>模型名称</td><td>${params.MODEL}</td></tr>
        <tr><td>模型路径</td><td>${params.MODEL_PATH}</td></tr>
        <tr><td>API 地址</td><td>${params.BASE_URL}</td></tr>
        <tr><td>PD分离模式</td><td>${params.PD}</td></tr>
        <tr><td>数据集类型</td><td>${params.DATASET_TYPE}</td></tr>
        ${datasetInfoRow}
        <tr><td>测试轮数</td><td>${round} 轮 (Run ID: ${runIdList})</td></tr>
        <tr><td>随机范围比例</td><td>${params.RANDOM_RANGE_RATIO}</td></tr>
        <tr><td>执行时间</td><td>${currentBuild.durationString}</td></tr>
        <tr><td>测试状态</td><td>${testStatus}</td></tr>
    </table>

    <h3>测试报告内容</h3>
    ${reportHtml}

    <p style="margin-top: 20px;"><b>详细日志和报告已归档到 Jenkins 构建 artifacts 中。</b></p>
    <p>Jenkins 构建地址: <a href="${env.BUILD_URL}">${env.BUILD_URL}</a></p>
</div>
<div class="footer" style="margin-top: 20px; padding: 15px; background-color: #f9f9f9;">
    此邮件由 Jenkins 自动发送，请勿回复。
</div>
</div>
</body>
</html>"""

                        println("=== 发送邮件 ===")
                        println("报告数量: ${mdFiles ? mdFiles.length : 0}")
                        println("测试状态: ${testStatus}")

                        emailext(
                            subject: "[模型推理 - Benchmark测试报告] #${BUILD_NUMBER} ${params.CHIP} - ${params.MODEL} - ${round}轮测试 (${infra})",
                            body: emailBody,
                            to: "${params.RECIPIENTS}",
                            mimeType: 'text/html',
                            attachmentsPattern: "builds/${BUILD_NUMBER}/dashboard/**/*.md"
                        )
                    }
                }
            }
        }

        stage('解析并入库') {
            steps {
                catchError(buildResult: 'UNSTABLE', stageResult: 'FAILURE') {
                    script {
                        def curDate = new Date().format('yyyy-MM-dd')
                        def buildsDir = "builds/${BUILD_NUMBER}"
                        
                        println("=== 解析并入库测试结果 ===")
                        println("测试人员: ${params.TESTER}")
                        println("测试日期: ${curDate}")
                        
                        def mdFiles = findFiles(glob: "${buildsDir}/dashboard/**/*.md")
                        if (!mdFiles || mdFiles.length == 0) {
                            println("警告: 未找到 markdown 文件")
                            return
                        }
                        
                        def mdPaths = mdFiles.collect { it.path }.join(' ')
                        
                        sh "python3 import_benchmark.py --tester '${params.TESTER}' --test-date '${curDate}' --md-files ${mdPaths}"
                        
                        println("=== 解析入库完成 ===")
                    }
                }
            }
        }

        stage('清理容器') {
            steps {
                sshagent(credentials: ["${SSH_CREDENTIALS}"]) {
                    script {
                        def containerName = env.CONTAINER_NAME ?: "dashboard-model-bench-${params.CHIP}-${params.MODEL}-${BUILD_NUMBER}"
                        println("=== 清理容器: ${containerName} ===")

                        sh """
ssh -o StrictHostKeyChecking=no ${REMOTE_USER}@${REMOTE_HOST} << 'ENDSSH'
docker rm -f ${containerName} 2>/dev/null || true
echo "容器 ${containerName} 已删除"
docker ps | grep ${containerName} || echo "容器已清理完成"
ENDSSH
"""
                    }
                }
            }
        }
    }
    post {
        always {
            script {
                archiveArtifacts artifacts: "builds/${BUILD_NUMBER}/**", allowEmptyArchive: true, fingerprint: true
                println("构建完成: ${currentBuild.currentResult}")
            }
        }
        cleanup {
            cleanWs()
        }
    }
}