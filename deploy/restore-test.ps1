<# Restaura backup em projeto Compose separado, sem tocar na instalação beta. #>
param([Parameter(Mandatory=$true)][string]$BackupDirectory)
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
$root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$backup = (Resolve-Path -LiteralPath $BackupDirectory).Path
$manifestPath = Join-Path $backup 'manifest.json'
if (-not (Test-Path -LiteralPath $manifestPath)) { throw 'Manifesto do backup ausente.' }
$entries = @(Get-Content -LiteralPath $manifestPath -Raw | ConvertFrom-Json)
foreach ($entry in $entries) {
    $path = [System.IO.Path]::GetFullPath((Join-Path $backup $entry.path))
    if (-not $path.StartsWith($backup + [System.IO.Path]::DirectorySeparatorChar, [System.StringComparison]::OrdinalIgnoreCase)) {
        throw 'Manifesto contém caminho fora do backup.'
    }
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) { throw "Arquivo do backup ausente: $($entry.path)" }
    $digest = (Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash
    if ($digest -ne $entry.sha256 -or (Get-Item -LiteralPath $path).Length -ne $entry.bytes) {
        throw "Integridade do backup falhou: $($entry.path)"
    }
}
foreach ($required in @('database.dump', 'beta.env', 'secrets/django_secret', 'secrets/database_password', 'secrets/redis_password', 'secrets/sector_key')) {
    if (-not (Test-Path -LiteralPath (Join-Path $backup $required))) { throw "Backup incompleto: $required" }
}
$project = 'scribrief-restore-check'
$existing = & docker compose -p $project --env-file (Join-Path $backup 'beta.env') -f (Join-Path $root 'compose.beta.yaml') ps -q --all db
if ($LASTEXITCODE -ne 0 -or $existing) { throw 'Clone de restauração já existe ou não pôde ser verificado. Não sobrescrever.' }
$overlayDir = Join-Path $root 'release-out'
New-Item -ItemType Directory -Path $overlayDir -Force | Out-Null
$overlay = Join-Path $overlayDir 'restore-check-secrets.yaml'
if (Test-Path -LiteralPath $overlay) { throw 'Overlay de restauração já existe. Não sobrescrever.' }
$b = $backup.Replace('\','/')
@"
secrets:
  django_secret: {file: '$b/secrets/django_secret'}
  database_password: {file: '$b/secrets/database_password'}
  redis_password: {file: '$b/secrets/redis_password'}
  sector_key: {file: '$b/secrets/sector_key'}
"@ | Set-Content -LiteralPath $overlay
function Compose([string[]]$Arguments) {
    & docker compose -p $project --env-file (Join-Path $backup 'beta.env') -f (Join-Path $root 'compose.beta.yaml') -f $overlay @Arguments
    if ($LASTEXITCODE -ne 0) { throw "docker compose $($Arguments[0]) falhou ($LASTEXITCODE)" }
}
Push-Location $root
try {
    Compose @('config', '--quiet')
    Compose @('up', '-d', '--wait', 'db', 'redis')
    $dbId = & docker compose -p $project --env-file (Join-Path $backup 'beta.env') -f (Join-Path $root 'compose.beta.yaml') -f $overlay ps -q db
    if (-not $dbId) { throw 'Banco do clone não iniciado.' }
    & docker cp (Join-Path $backup 'database.dump') "${dbId}:/tmp/restore.dump"
    if ($LASTEXITCODE -ne 0) { throw 'Falha ao copiar dump ao clone.' }
    Compose @('exec', '-T', 'db', 'pg_restore', '--no-owner', '--clean', '--if-exists', '-U', 'scribrief', '-d', 'scribrief', '/tmp/restore.dump')
    $media = (Join-Path $backup 'media').Replace('\','/')
    Compose @('run', '--no-deps', '--rm', '-v', "${media}:/backup-media:ro", 'backend', 'sh', '-c', 'cp -R /backup-media/. /app/dados/')
    Compose @('run', '--no-deps', '--rm', '-v', "${b}:/backup:ro", '-v', "$($PSScriptRoot.Replace('\','/')):/deploy:ro", 'backend', 'python', '/deploy/check_restored_media.py', '/backup/manifest.json', '/app/dados')
    Compose @('up', '-d', 'backend')
    Compose @('exec', '-T', 'backend', 'python', 'manage.py', 'check')
    Compose @('exec', '-T', 'backend', 'python', 'manage.py', 'migrate', '--check', '--noinput')
    Write-Output "Restauração verificada no projeto isolado $project. Clone mantido para inspeção; nenhuma porta foi publicada."
} finally { Pop-Location }
