param(
    [ValidateRange(1, 65535)][int]$Port = 8000,
    [switch]$SkipInstall
)
$ErrorActionPreference = 'Stop'
$taskRoot = $PSScriptRoot
Push-Location -LiteralPath $taskRoot
try {
    $taskPython = Join-Path $taskRoot '.venv\Scripts\python.exe'
    if (-not (Test-Path -LiteralPath $taskPython)) {
        python -m venv .venv
        if ($LASTEXITCODE -ne 0) { throw 'Python 3.12 diperlukan. Instal Python lalu coba kembali.' }
    }
    if (-not $SkipInstall) {
        & $taskPython -m pip install -r face_demo/requirements.txt -c face_demo/constraints.txt
        if ($LASTEXITCODE -ne 0) { throw 'Instalasi dependensi gagal. Periksa koneksi dan log di atas.' }
    }
    & $taskPython -m face_demo --port $Port
    if ($LASTEXITCODE -ne 0) { throw 'Face Lab berhenti karena kesalahan. Periksa log di atas.' }
} finally {
    Pop-Location
}
