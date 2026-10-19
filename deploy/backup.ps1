<# Backup frio consistente do beta; destino deve ser volume corporativo cifrado. #>
param(
    [Parameter(Mandatory=$true)][string]$EncryptedDestination,
    [switch]$AcknowledgeProtectedStorage
)
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
if (-not $AcknowledgeProtectedStorage) { throw 'Confirme que o destino tem cifragem e ACL corporativa com -AcknowledgeProtectedStorage.' }
$root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$envPath = Join-Path $PSScriptRoot 'beta.env'
$composePath = Join-Path $root 'compose.beta.yaml'
$destination = [System.IO.Path]::GetFullPath($EncryptedDestination)
if ($destination -eq $root -or $destination.StartsWith($root + [System.IO.Path]::DirectorySeparatorChar, [System.StringComparison]::OrdinalIgnoreCase)) {
    throw 'Backup deve ficar fora da árvore do projeto.'
}
if (-not (Test-Path -LiteralPath $destination -PathType Container)) { throw 'Destino protegido não existe.' }
$backup = Join-Path $destination ('scribrief-beta-' + (Get-Date -Format 'yyyyMMdd-HHmmss'))
if (Test-Path -LiteralPath $backup) { throw 'Backup com esse nome já existe.' }
function Compose([string[]]$Arguments) {
    & docker compose --env-file $envPath -f $composePath @Arguments
    if ($LASTEXITCODE -ne 0) { throw "docker compose $($Arguments[0]) falhou ($LASTEXITCODE)" }
}
$frontendStopped = $false
$jobsStopped = $false
Push-Location $root
try {
    Compose @('stop', 'frontend')
    $frontendStopped = $true
    $activeCheck = 'from apps.meetings.models import Meeting,MeetingStatus,ProcessingJob,SpeakerAnalysis; import sys; active=ProcessingJob.objects.filter(status__in=["queued","running"]).exists() or Meeting.objects.filter(status__in=[MeetingStatus.EXTRAINDO_AUDIO,MeetingStatus.TRANSCREVENDO,MeetingStatus.GERANDO_ATA]).exists() or SpeakerAnalysis.objects.filter(status="processing").exists(); sys.exit(3 if active else 0)'
    & docker compose --env-file $envPath -f $composePath exec -T backend python manage.py shell -c $activeCheck
    if ($LASTEXITCODE -eq 3) { throw 'Há jobs ativos; backup recusado. Aguarde o fim e tente novamente.' }
    if ($LASTEXITCODE -ne 0) { throw 'Falha ao verificar jobs ativos; backup recusado.' }
    Compose @('stop', 'backend', 'worker', 'beat')
    $jobsStopped = $true
    New-Item -ItemType Directory -Path $backup, (Join-Path $backup 'media'), (Join-Path $backup 'secrets') | Out-Null
    Compose @('exec', '-T', 'db', 'pg_dump', '-Fc', '-U', 'scribrief', '-d', 'scribrief', '-f', '/tmp/scribrief-beta.dump')
    $dbId = & docker compose --env-file $envPath -f $composePath ps -q db
    $workerId = & docker compose --env-file $envPath -f $composePath ps -q --all worker
    if (-not $dbId -or -not $workerId) { throw 'Contêiner de banco ou worker não encontrado.' }
    & docker cp "${dbId}:/tmp/scribrief-beta.dump" (Join-Path $backup 'database.dump')
    if ($LASTEXITCODE -ne 0) { throw 'Falha ao copiar dump PostgreSQL.' }
    & docker cp "${workerId}:/app/dados/." (Join-Path $backup 'media')
    if ($LASTEXITCODE -ne 0) { throw 'Falha ao copiar volume de mídia.' }
    Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'beta.env') -Destination $backup
    Get-ChildItem -LiteralPath (Join-Path $PSScriptRoot 'secrets') -File |
        Copy-Item -Destination (Join-Path $backup 'secrets')
    $manifest = Get-ChildItem -LiteralPath $backup -Recurse -File | ForEach-Object {
        [pscustomobject]@{path=[System.IO.Path]::GetRelativePath($backup, $_.FullName); sha256=(Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash; bytes=$_.Length}
    }
    $manifest | ConvertTo-Json -Depth 3 | Set-Content -LiteralPath (Join-Path $backup 'manifest.json')
    Write-Output "Backup criado em $backup. Contém dados e segredos em claro; proteja-o e teste a restauração."
} finally {
    if ($jobsStopped) { try { Compose @('up', '-d', 'backend', 'worker', 'beat') } catch { Write-Warning "Falha ao reiniciar jobs: $_" } }
    if ($frontendStopped) { try { Compose @('up', '-d', 'frontend') } catch { Write-Warning "Falha ao reiniciar frontend: $_" } }
    Pop-Location
}
