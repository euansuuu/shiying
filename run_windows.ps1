$ErrorActionPreference = "Stop"
Set-Location -LiteralPath $PSScriptRoot
$pythonPath = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $pythonPath)) {
    throw "请先执行 python -m venv .venv，再安装 desktop\requirements.txt 中的依赖。"
}
& $pythonPath -m desktop
exit $LASTEXITCODE
