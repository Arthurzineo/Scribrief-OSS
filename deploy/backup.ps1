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
$running = @{}
foreach ($service in @('frontend', 'backend', 'worker', 'beat', 'db', 'redis')) {
    $containerId = & docker compose --env-file $envPath -f $composePath ps -q $service
    if ($LASTEXITCODE -ne 0 -or -not $containerId) { throw "Serviço $service não está em execução; backup recusado." }
    $expectedLine = & docker compose --env-file $envPath -f $composePath config --hash $service
    if ($LASTEXITCODE -ne 0 -or -not $expectedLine) { throw "Não foi possível verificar configuração de $service." }
    $expectedHash = (($expectedLine | Select-Object -Last 1) -split '\s+')[-1]
    $actualHash = & docker inspect $containerId --format '{{index .Config.Labels "com.docker.compose.config-hash"}}'
    if ($LASTEXITCODE -ne 0 -or -not $actualHash -or $expectedHash -ne $actualHash.Trim()) {
        throw "Configuração de $service difere do contêiner ativo. Backup recusado antes de parar serviços; use o Compose da instalação ativa ou faça migração controlada."
    }
    $running[$service] = $containerId.Trim()
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
    New-Item -ItemType Directory -Path $backup, (Join-Path $backup 'media'), (Join-Path $backup 'secrets'), (Join-Path $backup 'tls') | Out-Null
    Compose @('exec', '-T', 'db', 'pg_dump', '-Fc', '-U', 'scribrief', '-d', 'scribrief', '-f', '/tmp/scribrief-beta.dump')
    $dbId = $running['db']
    $workerId = $running['worker']
    $backendId = $running['backend']
    if (-not $dbId -or -not $workerId -or -not $backendId) { throw 'Contêiner de banco, backend ou worker não encontrado.' }
    & docker cp "${dbId}:/tmp/scribrief-beta.dump" (Join-Path $backup 'database.dump')
    if ($LASTEXITCODE -ne 0) { throw 'Falha ao copiar dump PostgreSQL.' }
    & docker cp "${workerId}:/app/dados/." (Join-Path $backup 'media')
    if ($LASTEXITCODE -ne 0) { throw 'Falha ao copiar volume de mídia.' }
    & docker cp "${backendId}:/app/tls/current.pem" (Join-Path $backup 'tls/current.pem')
    if ($LASTEXITCODE -ne 0) { throw 'Falha ao copiar certificado TLS.' }
    Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'beta.env') -Destination $backup
    Get-ChildItem -LiteralPath (Join-Path $PSScriptRoot 'secrets') -File |
        Copy-Item -Destination (Join-Path $backup 'secrets')
    $manifest = Get-ChildItem -LiteralPath $backup -Recurse -File | ForEach-Object {
        [pscustomobject]@{path=[System.IO.Path]::GetRelativePath($backup, $_.FullName); sha256=(Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash; bytes=$_.Length}
    }
    $manifest | ConvertTo-Json -Depth 3 | Set-Content -LiteralPath (Join-Path $backup 'manifest.json')
    Write-Output "Backup criado em $backup. Contém dados e segredos em claro; proteja-o e teste a restauração."
} finally {
    if ($jobsStopped) {
        foreach ($service in @('backend', 'worker', 'beat')) {
            & docker start $running[$service] | Out-Null
            if ($LASTEXITCODE -ne 0) { Write-Warning "Falha ao reiniciar contêiner original de $service." }
        }
    }
    if ($frontendStopped) {
        & docker start $running['frontend'] | Out-Null
        if ($LASTEXITCODE -ne 0) { Write-Warning 'Falha ao reiniciar contêiner original do frontend.' }
    }
    Pop-Location
}
