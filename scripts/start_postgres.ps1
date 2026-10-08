# Starts the existing portable PostgreSQL 17 cluster for the DJ-App project.
$ErrorActionPreference = "Stop"

$PG_ROOT = "C:\ProgramData\pgsql17"
$PG_HOME = Join-Path $PG_ROOT "pgsql"
$DATA_DIR = Join-Path $PG_ROOT "data"
$POSTGRES_EXE = Join-Path $PG_HOME "bin\postgres.exe"
$LOG_FILE = Join-Path $PG_ROOT ("server-autostart-{0}.log" -f (Get-Date -Format "yyyyMMdd-HHmmss-fff"))

if (-not (Test-Path -LiteralPath $POSTGRES_EXE -PathType Leaf)) {
    throw "PostgreSQL executable not found: $POSTGRES_EXE"
}
if (-not (Test-Path -LiteralPath (Join-Path $DATA_DIR "PG_VERSION") -PathType Leaf)) {
    throw "Existing PostgreSQL data directory not found: $DATA_DIR"
}

function Test-PostgresPort {
    $client = New-Object System.Net.Sockets.TcpClient
    try {
        $pending = $client.BeginConnect("127.0.0.1", 5432, $null, $null)
        if (-not $pending.AsyncWaitHandle.WaitOne(500, $false)) {
            return $false
        }
        $client.EndConnect($pending)
        return $true
    } catch [System.Net.Sockets.SocketException] {
        return $false
    } finally {
        $client.Close()
    }
}

$running = Get-Process -Name "postgres" -ErrorAction SilentlyContinue
if ($running -and (Test-PostgresPort)) {
    Write-Host "PostgreSQL is already listening on 127.0.0.1:5432."
    exit 0
}

if (-not $running) {
    $process = Start-Process `
        -FilePath $POSTGRES_EXE `
        -ArgumentList @("-D", $DATA_DIR) `
        -WorkingDirectory $PG_ROOT `
        -WindowStyle Hidden `
        -RedirectStandardError $LOG_FILE `
        -PassThru
    Write-Host "Started PostgreSQL process $($process.Id); startup log: $LOG_FILE"
}

$ready = $false
for ($i = 0; $i -lt 30; $i++) {
    if (Test-PostgresPort) {
        $ready = $true
        break
    }
    Start-Sleep -Milliseconds 500
}

if (-not $ready) {
    throw "PostgreSQL did not become ready on 127.0.0.1:5432. Check $LOG_FILE"
}

Write-Host "PostgreSQL is ready on 127.0.0.1:5432 (data: $DATA_DIR)"
