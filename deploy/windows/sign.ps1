<#
.SYNOPSIS
    Code-signing wrapper for the pechepro Windows installer (V0.1 stub).

.DESCRIPTION
    V0.1 ships UNSIGNED. This script prints a "pending" notice so it can be
    wired into the CI pipeline (release.yml) without breaking the build, and
    so the team has a single place to swap in real signtool.exe logic when a
    code-signing certificate is available.

    Acquiring an EV Code Signing certificate (DigiCert / Sectigo / SSL.com,
    ~70-200 USD per year) eliminates the SmartScreen "Unknown publisher"
    warning on first launch. Until then, V0.1 users must click
    "More info" -> "Run anyway" the first time they run pechepro-setup.exe.

.PARAMETER TargetPath
    Path to the .exe to sign. Defaults to dist\pechepro-setup.exe relative to
    the repo root. Accepted for forward compatibility with the V0.2 signtool
    implementation.

.NOTES
    Exit code is always 0 so this script never blocks CI in V0.1.

    V0.2 unlock plan (replace the body of this script):
        $signtool = "${env:ProgramFiles(x86)}\Windows Kits\10\bin\<sdk>\x64\signtool.exe"
        & $signtool sign /fd SHA256 /tr http://timestamp.digicert.com /td SHA256 `
                         /a /n "Master / sxc3030-eng" $TargetPath
        if ($LASTEXITCODE -ne 0) { throw "signtool failed: $LASTEXITCODE" }
#>
[CmdletBinding()]
param(
    [string] $TargetPath = "dist\pechepro-setup.exe"
)

Write-Host "==> sign.ps1 (V0.1 stub)" -ForegroundColor Cyan
Write-Host "    Target: $TargetPath"
Write-Host ""
Write-Host "    V0.2: code signing pending - acquire EV Code Signing certificate" -ForegroundColor Yellow
Write-Host "          (~70-200 USD/yr) to eliminate SmartScreen warning." -ForegroundColor Yellow
Write-Host ""
Write-Host "    V0.1 installer ships unsigned. End-users will see the SmartScreen" -ForegroundColor Yellow
Write-Host "    'Unknown publisher' warning on first launch and must click" -ForegroundColor Yellow
Write-Host "    'More info' -> 'Run anyway' to proceed." -ForegroundColor Yellow

exit 0
