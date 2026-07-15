# 查看信息智能分析系统状态 (Windows PowerShell)
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$PidFile = Join-Path $ScriptDir "logs\server.pid"
$Port = if ($env:ISAS_SERVER_PORT) { $env:ISAS_SERVER_PORT } else { "8000" }

if (Test-Path $PidFile) {
  $pidVal = [int](Get-Content $PidFile)
  $proc = Get-Process -Id $pidVal -ErrorAction SilentlyContinue
  if ($proc) {
    Write-Host "运行中 (PID $pidVal)"
    try {
      $resp = (Invoke-WebRequest "http://127.0.0.1:$Port/api/health" -UseBasicParsing -TimeoutSec 3).Content
      Write-Host "健康检查: OK ($resp)"
    } catch {
      Write-Host "健康检查: 失败 (端口 $Port 无响应)"
    }
    exit 0
  } else {
    Write-Host "PID $pidVal 未运行"; exit 1
  }
} else {
  Write-Host "未运行（无 PID 文件）"; exit 1
}
