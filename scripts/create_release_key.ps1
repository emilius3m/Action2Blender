$ErrorActionPreference = 'Stop'

$privateDirectory = Join-Path $env:USERPROFILE '.action2blender'
$keystore = Join-Path $privateDirectory 'release.jks'
$secret = Join-Path $privateDirectory 'release-password.dpapi'
if ((Test-Path -LiteralPath $keystore) -or (Test-Path -LiteralPath $secret)) {
    throw 'Release key already exists. Do not replace a published signing key.'
}

New-Item -ItemType Directory -Path $privateDirectory -Force | Out-Null
$randomBytes = [byte[]]::new(48)
[System.Security.Cryptography.RandomNumberGenerator]::Fill($randomBytes)
$password = [Convert]::ToBase64String($randomBytes)
$secure = ConvertTo-SecureString -String $password -AsPlainText -Force
$encrypted = ConvertFrom-SecureString -SecureString $secure
[System.IO.File]::WriteAllText($secret, $encrypted)

$env:A2B_RELEASE_PASSWORD = $password
try {
    & keytool.exe -genkeypair -keystore $keystore -alias action2blender `
        -keyalg RSA -keysize 4096 -validity 10000 -dname 'CN=Action2Blender, O=Action2Blender, C=IT' `
        -storepass:env A2B_RELEASE_PASSWORD -keypass:env A2B_RELEASE_PASSWORD -noprompt
    if ($LASTEXITCODE -ne 0) { throw 'keytool could not create the release key.' }
} finally {
    Remove-Item Env:A2B_RELEASE_PASSWORD -ErrorAction SilentlyContinue
    $password = $null
}

Write-Output "Release keystore: $keystore"
Write-Output "Encrypted password: $secret"
