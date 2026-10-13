param(
    [ValidateRange(1024, 65535)][int]$Port = 5000,
    [switch]$Background
)

$ErrorActionPreference = 'Stop'
$projectRoot = $PSScriptRoot
$projectPython = Join-Path $projectRoot '.venv\Scripts\python.exe'
$entryPoint = Join-Path $projectRoot 'project\run.py'
$demoDatabase = Join-Path $projectRoot 'project\instance\campus-clubs.sqlite3'

if (-not (Test-Path -LiteralPath $projectPython)) {
    throw '请先按 project/README.md 创建 .venv 并安装项目依赖。'
}

$portListeners = @(Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue)
if ($portListeners.Count -gt 0) {
    $listenerIds = ($portListeners.OwningProcess | Sort-Object -Unique) -join ', '
    throw "端口 $Port 已被占用（PID：$listenerIds）。请使用该服务的实际地址或选择其他端口。"
}

# 只为尚不存在的本地数据库建立课程演示数据，已有记录原样保留。
if (-not (Test-Path -LiteralPath $demoDatabase)) {
    & $projectPython -X utf8 $entryPoint init-demo
    if ($LASTEXITCODE -ne 0) { throw '演示数据初始化失败。' }
}

if ($Background) {
    $logPrefix = Join-Path $projectRoot ("project\instance\preview-$Port-" + (Get-Date -Format 'yyyyMMdd-HHmmssfff'))
    $previewProcess = Start-Process -FilePath $projectPython `
        -ArgumentList @('-X', 'utf8', '-u', 'project/run.py', 'serve', '--port', $Port) `
        -WorkingDirectory $projectRoot -WindowStyle Hidden `
        -RedirectStandardOutput ($logPrefix + '.out.log') `
        -RedirectStandardError ($logPrefix + '.err.log') -PassThru
    $previewUrl = "http://127.0.0.1:$Port"
    $ready = $false
    for ($attempt = 0; $attempt -lt 30; $attempt++) {
        Start-Sleep -Milliseconds 300
        try {
            $previewRequest = [System.Net.HttpWebRequest]::Create($previewUrl + '/')
            $previewRequest.Proxy = $null
            $previewRequest.Timeout = 1000
            $previewResponse = $previewRequest.GetResponse()
            $ready = ([int]$previewResponse.StatusCode -eq 200)
            $previewResponse.Close()
            if ($ready) { break }
        } catch { }
        $previewProcess.Refresh()
        if ($previewProcess.HasExited) { break }
    }
    if (-not $ready) {
        Write-Output "服务未就绪，请检查日志：$logPrefix.err.log"
        Get-Content -LiteralPath ($logPrefix + '.err.log') -Tail 20
        throw '后台服务启动失败。'
    }
    $previewListener = @(Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue)
    Write-Output "预览地址：$previewUrl"
    Write-Output ('服务 PID：' + (($previewListener.OwningProcess | Sort-Object -Unique) -join ', '))
    Write-Output "启动进程 PID：$($previewProcess.Id)"
    Write-Output "运行日志：$logPrefix.out.log"
    Write-Output "错误日志：$logPrefix.err.log"
    exit 0
}

& $projectPython -X utf8 $entryPoint serve --port $Port
exit $LASTEXITCODE
