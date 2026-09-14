param([int]$Port = 8010)
$ErrorActionPreference = "Stop"
Set-Location -LiteralPath $PSScriptRoot
$projectPython = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $projectPython)) {
    throw "请先运行 setup.ps1 创建环境。"
}
& $projectPython scripts/dev.py --port $Port
exit $LASTEXITCODE
