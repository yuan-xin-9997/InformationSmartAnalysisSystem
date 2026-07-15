# 启动信息智能分析系统 (Windows PowerShell)
$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ScriptDir

$Venv = if ($env:ISAS_VENV) { $env:ISAS_VENV } else { Join-Path $ScriptDir ".venv" }
$PythonExe = Join-Path $Venv "Scripts\python.exe"
$LogDir = Join-Path $ScriptDir "logs"
$DataDir = Join-Path $ScriptDir "data"
$PidFile = Join-Path $LogDir "server.pid"

New-Item -ItemType Directory -Force -Path $LogDir, $DataDir, (Join-Path $DataDir "downloads") | Out-Null

# 首次部署：创建默认 password.txt
$PwFile = Join-Path $DataDir "password.txt"
if (-not (Test-Path $PwFile)) {
  @'
# 格式: username:password:role  (role 取值: admin | user)
# admin 默认拥有所有页面权限；user 的可见页面由管理员在权限管理页配置。
# 修改本文件后，新用户在下次登录时会自动同步到数据库。
admin:admin123:admin
'@ | Set-Content -Path $PwFile -Encoding UTF8
  Write-Host "已创建默认 $PwFile"
}

# 虚拟环境 + 依赖
if (-not (Test-Path $PythonExe)) {
  Write-Host "创建虚拟环境 $Venv ..."
  python -m venv $Venv
}
& $PythonExe -c "import fastapi" 2>$null
if ($LASTEXITCODE -ne 0) {
  Write-Host "安装后端依赖 ..."
  & $PythonExe -m pip install --upgrade pip -q
  & $PythonExe -m pip install -r (Join-Path $ScriptDir "app\backend\requirements.txt") -q
}

# 前端构建（dist 不存在且 npm 可用时）
$Dist = Join-Path $ScriptDir "app\frontend\dist"
if (-not (Test-Path $Dist) -and (Get-Command npm -ErrorAction SilentlyContinue)) {
  Write-Host "构建前端 ..."
  Push-Location (Join-Path $ScriptDir "app\frontend")
  try { npm install --no-audit --no-fund; npm run build } catch { Write-Host "警告: 前端构建失败，将仅提供后端 API" }
  Pop-Location
}

# 已在运行则提示
if (Test-Path $PidFile) {
  $existing = [int](Get-Content $PidFile)
  if (Get-Process -Id $existing -ErrorAction SilentlyContinue) {
    Write-Host "服务已在运行 (PID $existing)"; exit 0
  }
}

$Host_ = if ($env:ISAS_SERVER_HOST) { $env:ISAS_SERVER_HOST } else { "0.0.0.0" }
# 端口优先取 ISAS_SERVER_PORT 环境变量；否则读 config/app.json；均失败回落 28080
if (-not $env:ISAS_SERVER_PORT) {
  try { $env:ISAS_SERVER_PORT = (Get-Content (Join-Path $ScriptDir "config\app.json") -Raw | ConvertFrom-Json).server.port.ToString() }
  catch { $env:ISAS_SERVER_PORT = "28080" }
}
$Port = $env:ISAS_SERVER_PORT
$ServerOut = Join-Path $LogDir "server.out"
$ServerErr = Join-Path $LogDir "server.err"
$proc = Start-Process -FilePath $PythonExe `
  -ArgumentList "-m","uvicorn","app.backend.main:app","--host",$Host_,"--port",$Port `
  -WorkingDirectory $ScriptDir -WindowStyle Hidden `
  -RedirectStandardOutput $ServerOut -RedirectStandardError $ServerErr -PassThru
$proc.Id | Set-Content $PidFile
Write-Host "服务已启动 (PID $($proc.Id))，监听 ${Host_}:${Port}"
