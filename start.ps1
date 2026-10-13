param([ValidateRange(1024, 65535)][int]$Port = 5000)

$ErrorActionPreference = 'Stop'
$projectRoot = $PSScriptRoot
$projectPython = Join-Path $projectRoot '.venv\Scripts\python.exe'
$entryPoint = Join-Path $projectRoot 'project\run.py'
$demoDatabase = Join-Path $projectRoot 'project\instance\campus-clubs.sqlite3'

if (-not (Test-Path -LiteralPath $projectPython)) {
    throw '请先按 project/README.md 创建 .venv 并安装项目依赖。'
}

# 只为尚不存在的本地数据库建立课程演示数据，已有记录原样保留。
if (-not (Test-Path -LiteralPath $demoDatabase)) {
    & $projectPython $entryPoint init-demo
    if ($LASTEXITCODE -ne 0) { throw '演示数据初始化失败。' }
}

& $projectPython $entryPoint serve --port $Port
exit $LASTEXITCODE
