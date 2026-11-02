$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
& .\.venv\Scripts\python.exe -m PyInstaller --noconfirm packaging\beast-pick.spec
if ($LASTEXITCODE -ne 0) { throw '打包失败' }
& .\.venv\Scripts\python.exe tools\check_bundle.py
if ($LASTEXITCODE -ne 0) { throw '打包程序启动检查失败，禁止交付此版本' }
Write-Output (Join-Path $PSScriptRoot 'dist\BP.exe')
