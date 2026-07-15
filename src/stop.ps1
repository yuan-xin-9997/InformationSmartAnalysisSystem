# 停止信息智能分析系统 (Windows PowerShell)
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$PidFile = Join-Path $ScriptDir "logs\server.pid"

if (-not (Test-Path $PidFile)) {
  Write-Host "未找到 PID 文件，服务可能未运行"; exit 0
}
$pidVal = [int](Get-Content $PidFile)
$proc = Get-Process -Id $pidVal -ErrorAction SilentlyContinue
if ($proc) {
  Stop-Process -Id $pidVal -Force
  Write-Host "已停止服务 (PID $pidVal)"
} else {
  Write-Host "进程 $pidVal 未运行"
}
Remove-Item $PidFile -Force -ErrorAction SilentlyContinue
