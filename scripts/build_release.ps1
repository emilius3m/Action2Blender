$ErrorActionPreference = 'Stop'

$privateDirectory = Join-Path $env:USERPROFILE '.action2blender'
$keystore = Join-Path $privateDirectory 'release.jks'
$secret = Join-Path $privateDirectory 'release-password.dpapi'
if (-not (Test-Path -LiteralPath $keystore) -or -not (Test-Path -LiteralPath $secret)) {
    throw 'Release key is missing. Run scripts/create_release_key.ps1 first.'
}

$secure = Get-Content -LiteralPath $secret -Raw | ConvertTo-SecureString
$pointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
try {
    $env:A2B_RELEASE_PASSWORD = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($pointer)
} finally {
    [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($pointer)
}
$env:A2B_RELEASE_STORE_FILE = $keystore
try {
    flutter build apk --release
    if ($LASTEXITCODE -ne 0) { throw 'Release APK build failed.' }
} finally {
    Remove-Item Env:A2B_RELEASE_PASSWORD -ErrorAction SilentlyContinue
    Remove-Item Env:A2B_RELEASE_STORE_FILE -ErrorAction SilentlyContinue
}
