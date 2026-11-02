param([switch]$NoErrorDialog)
$ErrorActionPreference = 'Stop'
$stage = [IO.Path]::GetFullPath($PSScriptRoot)
$statusFile = Join-Path $stage 'status.json'
$replaced = $false
$newProcess = $null
$oldExited = $false

function Write-Status([string]$state, [string]$message = '') {
    @{state=$state; message=$message} | ConvertTo-Json -Compress | Set-Content -LiteralPath $statusFile -Encoding UTF8
}

function Replace-WithRetry([string]$source, [string]$destination, [string]$backupPath) {
    for ($attempt=0; $attempt -lt 60; $attempt++) {
        try { [IO.File]::Replace($source, $destination, $backupPath); return }
        catch { if ($attempt -eq 59) { throw }; Start-Sleep -Milliseconds 200 }
    }
}

function Get-Digest([string]$path) {
    $stream = [IO.File]::OpenRead($path)
    $sha = [Security.Cryptography.SHA256]::Create()
    try { return ([BitConverter]::ToString($sha.ComputeHash($stream))).Replace('-', '').ToLowerInvariant() }
    finally { $sha.Dispose(); $stream.Dispose() }
}

try {
    $plan = Get-Content -LiteralPath (Join-Path $stage 'plan.json') -Raw -Encoding UTF8 | ConvertFrom-Json
    $target = [IO.Path]::GetFullPath([string]$plan.target)
    $directory = [IO.Path]::GetDirectoryName($target)
    if ([IO.Path]::GetDirectoryName($stage) -ne $directory -or [IO.Path]::GetFileName($stage) -notlike '.bp-update-*' -or [IO.Path]::GetExtension($target) -ne '.exe') { throw 'Invalid update location' }
    if ((Get-Item -LiteralPath $stage).Attributes -band [IO.FileAttributes]::ReparsePoint) { throw 'Invalid update directory' }
    $payload = Join-Path $stage 'new.exe'
    $backup = Join-Path $stage 'old.exe'
    if ((Get-Digest $payload) -ne $plan.payload_sha256) { throw 'Update checksum mismatch' }
    if ((Get-Digest $target) -ne $plan.current_sha256) { throw 'Current EXE changed during update' }
    $oldProcess = Get-Process -Id ([int]$plan.parent_pid) -ErrorAction SilentlyContinue
    if ($oldProcess) { $null = $oldProcess.Handle }
    Write-Status 'ready'
    if ($oldProcess -and -not $oldProcess.WaitForExit(60000)) { throw 'Current program did not exit' }
    $oldExited = $true
    if ((Get-Digest $target) -ne $plan.current_sha256) { throw 'Current EXE changed during update' }
    if ((Get-Digest $payload) -ne $plan.payload_sha256) { throw 'Update checksum mismatch' }
    Replace-WithRetry $payload $target $backup
    $replaced = $true
    $newProcess = Start-Process -FilePath $target -WorkingDirectory $directory -ArgumentList @('--complete-update', ('"' + $stage + '"')) -PassThru
    $started = Join-Path $stage 'started'
    for ($attempt=0; $attempt -lt 150; $attempt++) {
        if (Test-Path -LiteralPath $started) { break }
        if ($newProcess.HasExited) { throw 'New program failed to start' }
        Start-Sleep -Milliseconds 200
    }
    if (-not (Test-Path -LiteralPath $started)) { throw 'New program startup timed out' }
    # The new window is open. Delete the old EXE and only our own staging files.
    Set-Location -LiteralPath $directory
    foreach ($name in @('old.exe', 'plan.json', 'started', 'status.json', 'apply.ps1')) {
        Remove-Item -LiteralPath (Join-Path $stage $name) -Force -ErrorAction SilentlyContinue
    }
    Remove-Item -LiteralPath $stage -ErrorAction SilentlyContinue
    exit 0
} catch {
    $failure = $_.Exception.Message
    try {
        if ($replaced) {
            if ($newProcess -and -not $newProcess.HasExited) {
                & "$env:SystemRoot\System32\taskkill.exe" /PID $newProcess.Id /T /F | Out-Null
            }
            Replace-WithRetry $backup $target (Join-Path $stage 'failed.exe')
        }
        if ($oldExited -and (Get-Digest $target) -eq $plan.current_sha256) { Start-Process -FilePath $target -WorkingDirectory $directory -ArgumentList '--skip-update-check' | Out-Null }
    } catch { $failure += '; rollback: ' + $_.Exception.Message }
    Write-Status 'failed' $failure
    if ($oldExited -and -not $NoErrorDialog) {
        Add-Type -AssemblyName System.Windows.Forms
        [Windows.Forms.MessageBox]::Show(('更新未完成，已尝试恢复旧版。' + "`n" + $failure), 'BP 更新失败') | Out-Null
    }
    exit 1
}
