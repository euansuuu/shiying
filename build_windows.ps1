param([string]$OutputDirectory = "dist")

$ErrorActionPreference = "Stop"
Set-Location -LiteralPath $PSScriptRoot
$pythonPath = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $pythonPath)) {
    & python -m venv .venv
    if ($LASTEXITCODE -ne 0) { throw "创建 Python 环境失败。" }
}
& $pythonPath -m pip install -r desktop\requirements.lock.txt
if ($LASTEXITCODE -ne 0) { throw "安装桌面依赖失败。" }
& $pythonPath -m desktop.make_icon
if ($LASTEXITCODE -ne 0) { throw "生成应用图标失败。" }
& $pythonPath -m PyInstaller --noconfirm --clean --distpath $OutputDirectory desktop\Shiying.spec
if ($LASTEXITCODE -ne 0) { throw "打包失败。" }
$applicationDirectory = Join-Path $OutputDirectory "Shiying"
Copy-Item -LiteralPath "WINDOWS_GUIDE.md" -Destination (Join-Path $applicationDirectory "使用说明.md")
Write-Output "EXE: $((Resolve-Path -LiteralPath $applicationDirectory).Path)\Shiying.exe"
