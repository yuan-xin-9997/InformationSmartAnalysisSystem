# 查看信息智能分析系统状态 (Windows PowerShell)
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$PidFile = Join-Path $ScriptDir "logs\server.pid"
# 端口优先取 ISAS_SERVER_PORT 环境变量；否则读 config/app.json；均失败回落 28080
if (-not $env:ISAS_SERVER_PORT) {
  try { $env:ISAS_SERVER_PORT = (Get-Content (Join-Path $ScriptDir "config\app.json") -Raw | ConvertFrom-Json).server.port.ToString() }
  catch { $env:ISAS_SERVER_PORT = "28080" }
}
$Port = $env:ISAS_SERVER_PORT

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
