$ErrorActionPreference = 'Stop'

$expectedRoot = 'C:\Users\Anshika Tyagi\OneDrive\Desktop\DJ App\DJ-App'
$expectedHost = 'dpg-db967oqvcj2c73ahq3hg-a.oregon-postgres.render.com'
$expectedDatabase = 'dj_app_staging_pg'
$guardDirectory = Join-Path $env:LOCALAPPDATA 'DJ-App'
$guardPath = Join-Path $guardDirectory 'render-staging-db-migration-attempted'

$secureUrl = $null
$urlPointer = [IntPtr]::Zero
$databaseUrl = $null
$migrationStarted = $false

function Stop-Safely([string]$Message) {
    Write-Output "STOPPED: $Message"
}

try {
    $actualRoot = [IO.Path]::GetFullPath($PSScriptRoot).TrimEnd('\')
    $canonicalRoot = [IO.Path]::GetFullPath($expectedRoot).TrimEnd('\')
    if ($actualRoot -ine $canonicalRoot) {
        throw 'This script is not running from the expected DJ-App repository root.'
    }

    $gitRoot = (git -C $actualRoot rev-parse --show-toplevel).Trim()
    if ($LASTEXITCODE -ne 0 -or [IO.Path]::GetFullPath($gitRoot).TrimEnd('\') -ine $canonicalRoot) {
        throw 'Repository root verification failed.'
    }

    $pythonPath = Join-Path $actualRoot '.venv\Scripts\python.exe'
    if (-not (Test-Path -LiteralPath $pythonPath -PathType Leaf)) {
        throw 'The repository virtual-environment Python executable is missing.'
    }

    & $pythonPath -c 'import alembic, sqlalchemy, asyncpg' *> $null
    if ($LASTEXITCODE -ne 0) {
        throw 'Alembic or PostgreSQL Python dependencies are unavailable in the repository virtual environment.'
    }

    $upgradeProcesses = Get-CimInstance Win32_Process | Where-Object {
        $_.Name -match '^python(w)?\.exe$' -and
        $_.CommandLine -match 'alembic.*upgrade.*head'
    }
    if ($upgradeProcesses) {
        throw 'Another Alembic upgrade process appears to be running. No migration was started.'
    }

    if (-not $env:LOCALAPPDATA) {
        throw 'LOCALAPPDATA is unavailable; cannot create the one-attempt guard safely.'
    }
    if (Test-Path -LiteralPath $guardPath) {
        throw 'The one-attempt guard already exists. Do not rerun; inspect the prior attempt first.'
    }

    $secureUrl = Read-Host 'Enter the external URL for dj-app-staging-pg (hidden input)' -AsSecureString
    $urlPointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secureUrl)
    $databaseUrl = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($urlPointer)

    try {
        $databaseUri = [Uri]$databaseUrl
    } catch {
        throw 'The entered value is not a valid PostgreSQL URL. No migration was run.'
    }

    if (
        $databaseUri.Scheme -notmatch '^postgres(ql)?(\+asyncpg)?$' -or
        $databaseUri.Host -cne $expectedHost -or
        $databaseUri.AbsolutePath.Trim('/') -cne $expectedDatabase
    ) {
        throw 'The URL did not match the exact Render Oregon staging host and database name. No migration was run.'
    }

    New-Item -ItemType Directory -Path $guardDirectory -Force | Out-Null
    $guardStream = $null
    try {
        $guardStream = [IO.File]::Open(
            $guardPath,
            [IO.FileMode]::CreateNew,
            [IO.FileAccess]::Write,
            [IO.FileShare]::None
        )
        $guardBytes = [Text.Encoding]::ASCII.GetBytes('STAGING_MIGRATION_ATTEMPT_STARTED')
        $guardStream.Write($guardBytes, 0, $guardBytes.Length)
    } catch [IO.IOException] {
        throw 'Could not acquire the one-attempt guard. No migration was started.'
    } finally {
        if ($guardStream) {
            $guardStream.Dispose()
        }
    }

    $env:PYTHON_DOTENV_DISABLED = '1'
    $env:DATABASE_URL = $databaseUrl
    Write-Output 'Staging target validated. Running Alembic upgrade exactly once.'
    $migrationStarted = $true

    & $pythonPath -m alembic upgrade head *> $null
    $migrationExitCode = $LASTEXITCODE
    if ($migrationExitCode -ne 0) {
        throw "Alembic upgrade failed with exit code $migrationExitCode. The attempt guard remains; do not retry."
    }
    Write-Output 'ALEMBIC_UPGRADE=SUCCEEDED'

    $verificationCode = @"
import asyncio
import os
import sys
from sqlalchemy.ext.asyncio import create_async_engine

url = os.environ['DATABASE_URL']
if url.startswith('postgresql://'):
    url = url.replace('postgresql://', 'postgresql+asyncpg://', 1)

expected = {
    'users', 'role_master', 'song_requests', 'cached_songs',
    'downloaded_audios', 'refresh_tokens', 'user_search_history',
    'audio_assets'
}

async def main():
    engine = create_async_engine(url, pool_pre_ping=True)
    try:
        async with engine.connect() as connection:
            revision = (
                await connection.exec_driver_sql(
                    'SELECT version_num FROM alembic_version'
                )
            ).scalar_one_or_none()
            result = await connection.exec_driver_sql(
                "SELECT tablename FROM pg_tables WHERE schemaname = 'public'"
            )
            tables = {row[0] for row in result}
        missing = sorted(expected - tables)
        print('ALEMBIC_REVISION=' + str(revision))
        print('EXPECTED_TABLES_PRESENT=' + str(not missing))
        print('MISSING_TABLES=' + ','.join(missing))
        if missing:
            sys.exit(2)
    finally:
        await engine.dispose()

try:
    asyncio.run(main())
except Exception as error:
    print('SCHEMA_VERIFICATION_ERROR=' + type(error).__name__)
    sys.exit(3)
"@

    & $pythonPath -c $verificationCode
    if ($LASTEXITCODE -ne 0) {
        throw 'Migration succeeded but revision/table verification failed. The attempt guard remains; do not retry.'
    }

    foreach ($healthPath in @('/health/live', '/health/ready')) {
        $statusCode = & curl.exe --silent --show-error --max-time 90 `
            --output NUL --write-out '%{http_code}' `
            "https://dj-app-api-staging.onrender.com$healthPath"
        if ($LASTEXITCODE -ne 0) {
            Write-Output "$healthPath REQUEST_FAILED"
        } else {
            Write-Output "$healthPath HTTP=$statusCode"
        }
    }
} catch {
    Stop-Safely $_.Exception.Message
} finally {
    Remove-Item Env:DATABASE_URL -ErrorAction SilentlyContinue
    Remove-Item Env:PYTHON_DOTENV_DISABLED -ErrorAction SilentlyContinue
    if ($urlPointer -ne [IntPtr]::Zero) {
        [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($urlPointer)
    }
    if ($secureUrl) {
        $secureUrl.Dispose()
    }
    $databaseUrl = $null
    if ($migrationStarted) {
        Write-Output 'ONE_ATTEMPT_GUARD=RETAINED; do not rerun automatically.'
    }
}
