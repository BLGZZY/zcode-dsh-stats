[CmdletBinding()]
param(
    [string]$Asar,
    [string]$PythonPath
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

function Find-PersistentPython {
    param([string]$RequestedPython)
    # Resolve launchers to an absolute, installed interpreter used by later hooks.
    $probe = "import sys; from pathlib import Path; sys.exit(1) if sys.version_info < (3, 11) or sys.prefix != sys.base_prefix else None; print(Path(sys.executable).resolve())"
    if ($RequestedPython) {
        if (-not [System.IO.Path]::IsPathRooted($RequestedPython) -or -not (Test-Path -LiteralPath $RequestedPython -PathType Leaf)) {
            throw '-PythonPath must identify an existing absolute Python executable path.'
        }
        $result = & $RequestedPython -c $probe 2>$null
        if ($LASTEXITCODE -ne 0) { throw '-PythonPath must be Python 3.11+ from a persistent non-virtual installation.' }
        $candidate = ($result | Select-Object -Last 1)
        if ($null -eq $candidate -or -not [System.IO.Path]::IsPathRooted($candidate.Trim()) -or -not (Test-Path -LiteralPath $candidate.Trim() -PathType Leaf)) {
            throw 'The requested Python did not return a usable absolute executable path.'
        }
        return $candidate.Trim()
    }
    foreach ($name in @('py', 'python', 'python3')) {
        $command = Get-Command $name -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
        if ($null -eq $command) { continue }
        # Skip App Execution Alias stubs; probing them can open the Microsoft Store.
        if ($name -ne 'py' -and $command.Source -match '\\Microsoft\\WindowsApps\\python3?\.exe$') { continue }
        $probeArgs = @('-c', $probe)
        if ($name -eq 'py') { $probeArgs = @('-3') + $probeArgs }
        try {
            $result = & $command.Source @probeArgs 2>$null
            if ($LASTEXITCODE -ne 0) { continue }
            $candidate = ($result | Select-Object -Last 1)
            if ($null -eq $candidate) { continue }
            $candidate = $candidate.Trim()
            if ([System.IO.Path]::IsPathRooted($candidate) -and (Test-Path -LiteralPath $candidate -PathType Leaf)) {
                return $candidate
            }
        } catch { continue }
    }
    throw 'Python 3.11+ from a persistent installation is required. Use -PythonPath for an existing Python outside PATH; see docs/guide.md before installing another Python.'
}

try {
    if ($env:OS -ne 'Windows_NT') { throw 'This launcher is for Windows. Use Install.command / Remove.command or the Python CLI on macOS.' }
    $python = Find-PersistentPython -RequestedPython $PythonPath
    Write-Host "Using Python: $python"
    $targetArgs = @()
    if ($Asar) { $targetArgs = @('--asar', $Asar) }
    & $python (Join-Path $PSScriptRoot 'install.py') remove @targetArgs
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    Write-Host 'Loader removed and automatic restoration disabled. Fully quit and reopen ZCode when your active tasks finish.'
} catch {
    Write-Error -Message $_.Exception.Message -ErrorAction Continue
    exit 1
}
