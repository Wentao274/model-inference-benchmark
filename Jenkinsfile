pipeline {
    agent any
    parameters {
        choice(name: 'INFRA', choices: ['vllm', 'sglang'], description: '推理框架')
        string(name: 'CHIP', defaultValue: 'nvidia-h100', description: '芯片平台名称')
        string(name: 'MODEL', defaultValue: 'kimi-k2.5', description: '模型名称（served-model-name）')
        string(name: 'MODEL_PATH', defaultValue: '/dingofs/data1/userdata/llms/moonshotai/Kimi-K2.6', description: '模型路径')
        string(name: 'BASE_URL', defaultValue: 'http://10.201.149.10:8080', description: 'API 地址')
        string(name: 'TEST_SUITE', defaultValue: 'test_01', description: '测试套件（test_01, test_02）')
        string(name: 'RUN_ID', defaultValue: '01', description: '运行标识符（用于标识本次测试，默认 01）')
        string(name: 'COMPARE_WITH', defaultValue: '', description: '对比的运行 ID（可选，支持逗号分隔多个）')
        text(name: 'RECIPIENTS', defaultValue: 'liwt@zetyun.com', description: '邮件接收者（逗号分隔）')
        string(name: 'WORK_DIR', defaultValue: '/dingofs/data1/userdata/liwt/maas-image/model-inference-benchmark', description: '远程工作目录')
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
                        println("=== 环境检查 ===")
                        sh """
ssh -o StrictHostKeyChecking=no ${REMOTE_USER}@${REMOTE_HOST} << 'ENDSSH'
cd ${params.WORK_DIR}
echo "=== 工作目录 ==="
pwd
ls -la
echo "=== 测试参数信息 ==="
echo "推理框架: ${params.INFRA}"
echo "芯片类型: ${params.CHIP}"
echo "模型服务名称: ${params.MODEL}"
echo "模型路径: ${params.MODEL_PATH}"
echo "BASE_URL: ${params.BASE_URL}"
echo "测试套件: ${params.TEST_SUITE}"
echo "测试ID: ${params.RUN_ID}"
echo "比对ID: ${params.COMPARE_WITH}"
echo "BUILD_NUMBER: ${BUILD_NUMBER}"
echo "=== Docker 检查 ==="
docker --version
echo "=== 测试目录结构 ==="
ls -la config/
echo "=== 检查配置文件 ==="
cat config/test_suites.yaml
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
                    def image = infra == 'vllm' ? env.VLLM_IMAGE : env.SGLANG_IMAGE
                    def containerName = "model-bench-${params.CHIP}-${params.MODEL}-${BUILD_NUMBER}"
                    env.CONTAINER_NAME = containerName

                    println("=== 启动 ${infra.toUpperCase()} 容器 ===")
                    println("镜像: ${image}")
                    println("容器名: ${containerName}")
                    println("RUN_ID: ${params.RUN_ID}")

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
    --memory=32g \
    --shm-size=1g \
    --entrypoint bash \
    -v ${params.WORK_DIR}:/workspace/model-inference-benchmark \
    -v ${params.MODEL_PATH}:${params.MODEL_PATH} \
    -w /workspace/model-inference-benchmark \
    ${image} \
    -c "sleep infinity"

echo "=== 等待容器启动 ==="
sleep 20

echo "=== 容器状态 ==="
docker ps | grep ${containerName}

export https_proxy=http://100.64.1.68:1080
export http_proxy=http://100.64.1.68:1080
docker exec ${containerName} bash -c "cd /workspace/model-inference-benchmark && pip install -q -r requirements.txt || pip3 install -q -r requirements.txt"
unset https_proxy
unset http_proxy

echo "=== 检查 Python 命令 ==="
PYTHON_CMD=\$(docker exec ${containerName} bash -c "command -v python3 || command -v python || echo 'python3'")
echo "使用 Python 命令: \${PYTHON_CMD}"

echo "=== 执行 run_benchmark.py (RUN_ID: ${params.RUN_ID}) ==="
docker exec ${containerName} bash -c \
    "\${PYTHON_CMD} run_benchmark.py \
        --infra ${params.INFRA} \
        --base-url '${params.BASE_URL}' \
        --chip ${params.CHIP} \
        --model ${params.MODEL} \
        --model-path ${params.MODEL_PATH} \
        --test-suite ${params.TEST_SUITE} \
        --run-id ${params.RUN_ID}"

echo "=== Benchmark 执行完成 ==="
ENDSSH
"""
                        }
                    }
                }
            }
        }

        stage('生成报告') {
            steps {
                script {
                    def containerName = env.CONTAINER_NAME
                    def compareParam = params.COMPARE_WITH ? "--compare-with '${params.COMPARE_WITH}'" : ""

                    sshagent(credentials: ["${SSH_CREDENTIALS}"]) {
                        catchError(buildResult: 'UNSTABLE', stageResult: 'FAILURE') {
                            sh """
ssh -o StrictHostKeyChecking=no ${REMOTE_USER}@${REMOTE_HOST} << 'ENDSSH'
set -e
echo "=== 检查 Python 命令 ==="
PYTHON_CMD=\$(docker exec ${containerName} bash -c "command -v python3 || command -v python || echo 'python3'")
echo "使用 Python 命令: \${PYTHON_CMD}"

echo "=== 执行 generate_report.py (RUN_ID: ${params.RUN_ID}) ==="
docker exec ${containerName} bash -c \
    "\${PYTHON_CMD} generate_report.py \
        --infra ${params.INFRA} \
        --chip ${params.CHIP} \
        --model ${params.MODEL} \
        --test-suite ${params.TEST_SUITE} \
        --run-id ${params.RUN_ID} \
        ${compareParam}"

echo "=== 报告生成完成 ==="
ENDSSH
"""
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
                            def runId = params.RUN_ID ?: '01'
                            def compareWith = params.COMPARE_WITH ?: ''
                            
                            def reportsSrcPath = "reports/${params.INFRA}/benchmark/${params.CHIP}/${params.MODEL}/${params.TEST_SUITE}/${runId}"
                            def buildsDir = "builds/${BUILD_NUMBER}"
                            
                            def analysisSrcPath = ""
                            if (compareWith) {
                                def compareStr = compareWith.split(',').collect { it.trim() }.join('_')
                                analysisSrcPath = "analysis/${params.INFRA}/${params.CHIP}/${params.MODEL}/${params.TEST_SUITE}/compare_${runId}_${compareStr}"
                            } else {
                                analysisSrcPath = "analysis/${params.INFRA}/${params.CHIP}/${params.MODEL}/${params.TEST_SUITE}/${runId}"
                            }
                            
                            println("=== 备份测试结果到 ${buildsDir} ===")
                            
                            sh """
ssh -o StrictHostKeyChecking=no ${REMOTE_USER}@${REMOTE_HOST} << 'ENDSSH'
set -e
BUILDS_DIR=${params.WORK_DIR}/${buildsDir}
REPORTS_SRC=${params.WORK_DIR}/${reportsSrcPath}
ANALYSIS_SRC=${params.WORK_DIR}/${analysisSrcPath}

echo "=== 创建 builds 目录结构 ==="
mkdir -p "\${BUILDS_DIR}/reports/${params.INFRA}/benchmark/${params.CHIP}/${params.MODEL}/${params.TEST_SUITE}"
mkdir -p "\${BUILDS_DIR}/analysis/${params.INFRA}/${params.CHIP}/${params.MODEL}/${params.TEST_SUITE}"

echo "=== 复制 reports 到 builds 目录 ==="
if [ -d "\${REPORTS_SRC}" ]; then
    cp -r "\${REPORTS_SRC}" "\${BUILDS_DIR}/reports/${params.INFRA}/benchmark/${params.CHIP}/${params.MODEL}/${params.TEST_SUITE}/"
    echo "reports 复制完成: \${REPORTS_SRC} -> \${BUILDS_DIR}/reports/"
else
    echo "警告: reports 源目录不存在: \${REPORTS_SRC}"
fi

echo "=== 复制 analysis 到 builds 目录 ==="
if [ -d "\${ANALYSIS_SRC}" ]; then
    cp -r "\${ANALYSIS_SRC}" "\${BUILDS_DIR}/analysis/${params.INFRA}/${params.CHIP}/${params.MODEL}/${params.TEST_SUITE}/"
    echo "analysis 复制完成"
else
    echo "警告: analysis 源目录不存在: \${ANALYSIS_SRC}"
fi

echo "=== 备份完成，查看目录结构 ==="
find "\${BUILDS_DIR}" -type d | head -20
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
                        def runId = params.RUN_ID ?: '01'
                        def compareWith = params.COMPARE_WITH ?: ''
                        def buildsDir = "builds/${BUILD_NUMBER}"

                        def containerName = env.CONTAINER_NAME
                        def remoteTmpDir = "${params.WORK_DIR}/tmp"
                        def remoteJson = "${remoteTmpDir}/email_data_${BUILD_NUMBER}.json"
                        def remoteZip = "${remoteTmpDir}/benchmark_reports_${BUILD_NUMBER}.zip"
                        def localJson = "/tmp/email_data_${BUILD_NUMBER}.json"

                        sshagent(credentials: ["${SSH_CREDENTIALS}"]) {
                            sh """
ssh -o StrictHostKeyChecking=no ${REMOTE_USER}@${REMOTE_HOST} << 'ENDSSH'
mkdir -p ${remoteTmpDir}
docker exec ${containerName} python3 /workspace/model-inference-benchmark/generate_email.py \
    --builds-dir /workspace/model-inference-benchmark/${buildsDir} \
    --infra ${params.INFRA} \
    --chip ${params.CHIP} \
    --model ${params.MODEL} \
    --test-suite ${params.TEST_SUITE} \
    --run-id ${runId} \
    --compare-with '${compareWith}' \
    --build-number ${BUILD_NUMBER} \
    --output-json ${remoteJson} \
    --output-zip ${remoteZip}
ENDSSH
"""
                            sh """
scp -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null \
    ${REMOTE_USER}@${REMOTE_HOST}:${remoteJson} ${localJson}
scp -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null \
    ${REMOTE_USER}@${REMOTE_HOST}:${remoteZip} ${buildsDir}/benchmark_reports_${BUILD_NUMBER}.zip
"""
                        }

                        def emailDataText = readFile(localJson).trim()
                        def slurper = new groovy.json.JsonSlurper()
                        def emailData = slurper.parseText(emailDataText)

                        def reportCount = emailData.report_count
                        def reportBlocks = emailData.report_blocks
                        def logFileNames = emailData.log_file_names
                        def runTestStatus = emailData.test_status

                        def reportContents = ""
                        reportBlocks.each { b ->
                            reportContents += """
<div class="report-block">
<h3 style="margin-top: 0; color: #2196F3; border-bottom: 1px solid #ddd; padding-bottom: 10px;">${b.title}</h3>
<div class="report-content">${b.content}</div>
</div>
"""
                        }

                        def emailBody = """
<html>
<head>
    <meta charset="UTF-8">
    <style>
        body { font-family: Arial, sans-serif; margin: 0; padding: 20px; background-color: #f5f5f5; }
        .container { max-width: 1000px; margin: 0 auto; background-color: #fff; border-radius: 5px; box-shadow: 0 2px 5px rgba(0,0,0,0.1); }
        .header { background-color: ${reportCount > 0 ? '#2196F3' : '#f44336'}; color: white; padding: 20px; border-radius: 5px 5px 0 0; }
        .content { padding: 20px; }
        table { border-collapse: collapse; width: 100%; margin-top: 15px; }
        th, td { border: 1px solid #ddd; padding: 10px; text-align: left; }
        th { background-color: #f2f2f2; }
        h3 { color: #333; border-bottom: 2px solid #2196F3; padding-bottom: 5px; }
        .report-block { margin-bottom: 20px; border: 1px solid #ddd; padding: 15px; background-color: #fafafa; border-radius: 5px; }
        .report-content { font-size: 13px; line-height: 1.5; background-color: #f9f9f9; padding: 15px; border-radius: 3px; max-height: 600px; overflow-y: auto; }
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
        <tr><td>运行 ID</td><td>${runId}</td></tr>
        <tr><td>推理框架</td><td>${infra}</td></tr>
        <tr><td>被测芯片</td><td>${params.CHIP}</td></tr>
        <tr><td>被测模型</td><td>${params.MODEL}</td></tr>
        <tr><td>远程服务</td><td>${params.BASE_URL}</td></tr>
        <tr><td>执行时间</td><td>${currentBuild.durationString}</td></tr>
        <tr><td>测试状态</td><td>${runTestStatus}</td></tr>
    </table>

    <h3>测试配置</h3>
    <table>
        <tr><td><b>芯片平台</b></td><td>${params.CHIP}</td></tr>
        <tr><td><b>模型名称</b></td><td>${params.MODEL}</td></tr>
        <tr><td><b>模型路径</b></td><td>${params.MODEL_PATH}</td></tr>
        <tr><td><b>API 地址</b></td><td>${params.BASE_URL}</td></tr>
        <tr><td><b>测试套件</b></td><td>${params.TEST_SUITE}</td></tr>
"""
                        if (compareWith) {
                            emailBody += """
        <tr><td><b>对比运行 ID</b></td><td>${compareWith}</td></tr>
"""
                        }
                        emailBody += """
    </table>

    <h3>测试日志</h3>
    ${logFileNames}

    <h3>测试报告内容</h3>
    ${reportContents ?: '<p>无报告文件</p>'}

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
                        println("报告数量: ${reportCount}")
                        println("测试状态: ${runTestStatus}")

                        emailext(
                            subject: "[模型推理 - Benchmark测试报告] #${BUILD_NUMBER} ${params.CHIP} - ${params.MODEL} - RUN_ID:${runId} (${infra})",
                            body: emailBody,
                            to: "${params.RECIPIENTS}",
                            mimeType: 'text/html',
                            attachmentsPattern: "builds/${BUILD_NUMBER}/**"
                        )
                    }
                }
            }
        }

        stage('清理容器') {
            steps {
                sshagent(credentials: ["${SSH_CREDENTIALS}"]) {
                    script {
                        def containerName = env.CONTAINER_NAME ?: "model-bench-${params.CHIP}-${params.MODEL}-${BUILD_NUMBER}"
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