# Dot-source: . .\scripts\Enter-Environment.ps1
$WiiProjectRoot = Split-Path -Parent $PSScriptRoot
$env:DEVKITPRO = (Join-Path $WiiProjectRoot 'tools\devkitpro-root\opt\devkitpro').Replace('\','/')
$env:DEVKITPPC = "$env:DEVKITPRO/devkitPPC"
$WiiProjectBins = @((Join-Path $WiiProjectRoot '.venv\Scripts'), "$env:DEVKITPPC/bin", "$env:DEVKITPRO/tools/bin")
$env:PATH = ($WiiProjectBins -join [IO.Path]::PathSeparator) + [IO.Path]::PathSeparator + $env:PATH
Write-Output 'Project environment loaded for this PowerShell process only.'
