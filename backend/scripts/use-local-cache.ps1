<#
.SYNOPSIS
    Mantém todo download pesado dentro do disco do projeto.

.DESCRIPTION
    Por padrão o Windows espalha caches grandes pelo perfil do usuário (C:):

        pip          -> %LOCALAPPDATA%\pip\Cache          (~2,5 GB com torch)
        HuggingFace  -> %USERPROFILE%\.cache\huggingface  (~7 GB por modelo)
        TEMP         -> %LOCALAPPDATA%\Temp               (extração de wheels)
        torch hub    -> %USERPROFILE%\.cache\torch

    Este script aponta todos eles para `backend/data/cache/`, que fica no
    mesmo disco do projeto e é ignorado pelo git.

    O modelo em si já ia para o disco do projeto: a gaveta recebe
    `workspace_dir` da configuração e o usa como `cache_dir` do Diffusers.
    O que este script resolve são os caches que o AssetFlow não controla.

.PARAMETER Persist
    Grava as variáveis no perfil do usuário (setx), valendo para toda sessão
    futura e para qualquer projeto. Sem este parâmetro, vale só nesta janela.

.PARAMETER Root
    Pasta onde os caches serão criados. Padrão: backend/data/cache.

.EXAMPLE
    # Sessão atual (note o ponto no começo — precisa ser dot-sourced):
    . .\scripts\use-local-cache.ps1

.EXAMPLE
    # Permanente para o usuário:
    .\scripts\use-local-cache.ps1 -Persist
#>

[CmdletBinding()]
param(
    [switch]$Persist,
    [string]$Root
)

$ErrorActionPreference = 'Stop'

$backendRoot = Split-Path -Parent $PSScriptRoot
if (-not $Root) { $Root = Join-Path $backendRoot 'data\cache' }

$targets = [ordered]@{
    PIP_CACHE_DIR         = Join-Path $Root 'pip'
    HF_HOME               = Join-Path $Root 'huggingface'
    HUGGINGFACE_HUB_CACHE = Join-Path $Root 'huggingface\hub'
    TORCH_HOME            = Join-Path $Root 'torch'
    TMP                   = Join-Path $Root 'tmp'
    TEMP                  = Join-Path $Root 'tmp'
}

foreach ($path in ($targets.Values | Select-Object -Unique)) {
    if (-not (Test-Path $path)) { New-Item -ItemType Directory -Force -Path $path | Out-Null }
}

foreach ($name in $targets.Keys) {
    Set-Item -Path "env:$name" -Value $targets[$name]
    if ($Persist) { setx $name $targets[$name] | Out-Null }
}

$drive = (Split-Path -Qualifier $Root)
$free = (Get-PSDrive $drive.TrimEnd(':')).Free / 1GB

Write-Host ""
Write-Host "Caches redirecionados para $Root" -ForegroundColor Green
foreach ($name in $targets.Keys) {
    "{0,-22} {1}" -f $name, $targets[$name] | Write-Host
}
Write-Host ""
"{0,-22} {1:N1} GB livres" -f "disco $drive", $free | Write-Host

if ($Persist) {
    Write-Host "Gravado no perfil do usuário (vale em novas sessões)." -ForegroundColor Yellow
} else {
    Write-Host "Vale apenas nesta janela. Use -Persist para tornar permanente." -ForegroundColor DarkGray
}
Write-Host ""
