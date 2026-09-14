param([string]$Python = "python")
$ErrorActionPreference = "Stop"
Set-Location -LiteralPath $PSScriptRoot
if (-not (Test-Path -LiteralPath ".venv\Scripts\python.exe")) {
    & $Python -m venv .venv
    if ($LASTEXITCODE -ne 0) { throw "创建虚拟环境失败。" }
}
& .\.venv\Scripts\python.exe -m pip install -r requirements.lock.txt
if ($LASTEXITCODE -ne 0) { throw "依赖安装失败。" }
Write-Host "安装完成。运行 .\start.ps1 启动。"
