$ErrorActionPreference = "Stop"
Set-Location -LiteralPath $PSScriptRoot
$testDirectory = Join-Path $PSScriptRoot ('.test-runs/' + [guid]::NewGuid().ToString())
& .\.venv\Scripts\python.exe -m pytest -q --basetemp $testDirectory
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
& .\.venv\Scripts\python.exe -m ruff check --config pyproject.toml backend inference scripts tests migrations
exit $LASTEXITCODE
