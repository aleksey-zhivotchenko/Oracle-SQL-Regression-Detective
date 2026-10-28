$ErrorActionPreference = 'Stop'
$taskVenv = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
$taskPython = Get-Command python -ErrorAction SilentlyContinue
if (Test-Path -LiteralPath $taskVenv) {
    & $taskVenv @args
} elseif ($taskPython) {
    & $taskPython.Source @args
} else {
    $taskRuntime = Join-Path $env:USERPROFILE '.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe'
    if (-not (Test-Path -LiteralPath $taskRuntime)) { throw 'Install Python 3.10+ or add it to PATH.' }
    & $taskRuntime @args
}
exit $LASTEXITCODE
