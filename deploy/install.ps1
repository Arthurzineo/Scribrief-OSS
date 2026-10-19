<# Instalação beta em Windows 11/PowerShell 7 com Docker Desktop (Linux containers). #>
param(
    [string]$Certificate,
    [string]$PrivateKey,
    [switch]$SkipAdmin
)
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
$root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$compose = Join-Path $root 'compose.beta.yaml'
$envPath = Join-Path $PSScriptRoot 'beta.env'
$secretDir = Join-Path $PSScriptRoot 'secrets'
$certDir = Join-Path $PSScriptRoot 'certs'

function Require-Command([string]$Name) {
    if (-not (Get-Command $Name -ErrorAction SilentlyContinue)) { throw "Comando obrigatório ausente: $Name" }
}
function New-Secret([int]$Length, [bool]$Padded) {
    $bytes = [byte[]]::new($Length)
    [System.Security.Cryptography.RandomNumberGenerator]::Fill($bytes)
    $value = [Convert]::ToBase64String($bytes).Replace('+', '-').Replace('/', '_')
    if (-not $Padded) { return $value.TrimEnd('=') }
    return $value
}
function Write-NewSecret([string]$Name, [int]$Length, [bool]$Padded) {
    $path = Join-Path $secretDir $Name
    if (Test-Path -LiteralPath $path) {
        if ((Get-Item -LiteralPath $path).Length -lt 20) { throw "Segredo existente inválido: $Name" }
        return
    }
    $value = New-Secret $Length $Padded
    [System.IO.File]::WriteAllText($path, $value, [System.Text.UTF8Encoding]::new($false))
}
function Invoke-Compose([string[]]$Arguments) {
    & docker compose --env-file $envPath -f $compose @Arguments
    if ($LASTEXITCODE -ne 0) { throw "docker compose $($Arguments[0]) falhou ($LASTEXITCODE)" }
}

Require-Command 'docker'
& docker info --format '{{.ServerVersion}}' | Out-Null
if ($LASTEXITCODE -ne 0) { throw 'Docker daemon não está disponível.' }
& docker compose version | Out-Null
if ($LASTEXITCODE -ne 0) { throw 'Docker Compose plugin não está disponível.' }

if (-not (Test-Path -LiteralPath $envPath)) {
    Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'beta.env.example') -Destination $envPath
    Write-Output "Configuração criada em $envPath. Ajuste PUBLIC_BIND_IP/PUBLIC_HOSTNAME antes de uso na LAN."
}
New-Item -ItemType Directory -Path $secretDir, $certDir -Force | Out-Null
Write-NewSecret 'django_secret' 48 $false
Write-NewSecret 'database_password' 48 $false
Write-NewSecret 'redis_password' 48 $false
Write-NewSecret 'sector_key' 32 $true

if ($Certificate -xor $PrivateKey) { throw 'Informe Certificate e PrivateKey juntos.' }
$legacyImport = $false
if (-not $Certificate -and -not $PrivateKey) {
    $oldCert = Join-Path $certDir 'localhost.crt'
    $oldKey = Join-Path $certDir 'localhost.key'
    if ((Test-Path -LiteralPath $oldCert) -and (Test-Path -LiteralPath $oldKey)) {
        $Certificate = $oldCert; $PrivateKey = $oldKey; $legacyImport = $true
    }
}
if ($Certificate) {
    foreach ($source in @($Certificate, $PrivateKey)) {
        if (-not (Test-Path -LiteralPath $source -PathType Leaf)) { throw "Arquivo TLS não encontrado: $source" }
    }
    $Certificate = (Resolve-Path -LiteralPath $Certificate).Path
    $PrivateKey = (Resolve-Path -LiteralPath $PrivateKey).Path
}
& docker run --rm --network none -v "${PSScriptRoot}:/deploy:ro" python:3.12-slim-trixie@sha256:a6e34c598f2467ed0e9a8d349809fcd8b5c603269512df273a0bb1784edc11b1 python /deploy/check_tls.py /deploy --config-only
if ($LASTEXITCODE -ne 0) { throw 'Preflight TLS/configuração não aprovado.' }

Push-Location $root
try {
    Invoke-Compose @('config', '--quiet')
    Invoke-Compose @('build', 'backend')
    $tlsArgs = @('run', '--rm', '--no-deps', '--user', 'root', '--cap-add', 'CHOWN', '--cap-add', 'FOWNER', '--cap-add', 'DAC_OVERRIDE')
    if ($Certificate) {
        $tlsArgs += @('-v', "${Certificate}:/source/certificate:ro", '-v', "${PrivateKey}:/source/private-key:ro")
    }
    $tlsArgs += @('backend', 'python', '-m', 'apps.admin_panel.tls_bootstrap')
    if ($Certificate) { $tlsArgs += @('--certificate', '/source/certificate', '--private-key', '/source/private-key') }
    if ($legacyImport) { $tlsArgs += '--preserve-existing' }
    Invoke-Compose $tlsArgs
    Invoke-Compose @('up', '-d', '--build', 'db', 'redis', 'backend')
    Invoke-Compose @('exec', '-T', 'backend', 'python', 'manage.py', 'migrate', '--noinput')
    Invoke-Compose @('exec', '-T', 'backend', 'python', 'manage.py', 'check')
    Invoke-Compose @('up', '-d', '--build', 'worker', 'beat', 'frontend')
    Invoke-Compose @('ps')
    if (-not $SkipAdmin) {
        Write-Output 'Crie a primeira conta administrativa sem senha padrão:'
        Invoke-Compose @('exec', 'backend', 'python', 'manage.py', 'createsuperuser')
    }
    Write-Output 'Instalação beta concluída. Antes de receber dados reais, teste acesso de outra estação, TLS, firewall e backup/restore.'
} finally { Pop-Location }
