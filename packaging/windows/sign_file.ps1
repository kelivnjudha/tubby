param(
    [Parameter(Mandatory = $true)]
    [string]$FilePath
)

$ErrorActionPreference = "Stop"

if ([string]::IsNullOrWhiteSpace($env:WINDOWS_CERTIFICATE_PFX)) {
    Write-Host "Windows signing certificate is not configured; leaving $FilePath unsigned."
    exit 0
}

$certificatePath = Join-Path $env:RUNNER_TEMP "tubby-signing-certificate.pfx"
try {
    $certificateBytes = [Convert]::FromBase64String($env:WINDOWS_CERTIFICATE_PFX)
    [IO.File]::WriteAllBytes($certificatePath, $certificateBytes)

    $signTool = Get-ChildItem `
        -Path "${env:ProgramFiles(x86)}\Windows Kits\10\bin\*\x64\signtool.exe" `
        -ErrorAction SilentlyContinue |
        Sort-Object FullName -Descending |
        Select-Object -First 1 -ExpandProperty FullName
    if (-not $signTool) {
        throw "signtool.exe was not found on the Windows runner."
    }

    & $signTool sign `
        /fd SHA256 `
        /td SHA256 `
        /tr "http://timestamp.digicert.com" `
        /f $certificatePath `
        /p $env:WINDOWS_CERTIFICATE_PASSWORD `
        $FilePath
    if ($LASTEXITCODE -ne 0) {
        throw "signtool.exe could not sign $FilePath."
    }
}
finally {
    Remove-Item -LiteralPath $certificatePath -Force -ErrorAction SilentlyContinue
}
