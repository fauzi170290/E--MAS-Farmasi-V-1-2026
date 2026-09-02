$ErrorActionPreference = "Stop"

$mysql = "C:\xampp\mysql\bin\mysql.exe"
$database = "sik_emss_uji_lokal"
$username = "emss_readonly"
$hostName = "127.0.0.1"
$views = @(
    "vw_emss_prescription_header",
    "vw_emss_prescription_item",
    "vw_emss_compound_item",
    "vw_emss_drug_master"
)

if (-not (Test-Path -LiteralPath $mysql)) {
    throw "MySQL XAMPP tidak ditemukan di C:\xampp\mysql\bin\mysql.exe"
}

$randomBytes = New-Object byte[] 32
$generator = [Security.Cryptography.RandomNumberGenerator]::Create()
try {
    $generator.GetBytes($randomBytes)
} finally {
    $generator.Dispose()
}
$password = ([BitConverter]::ToString($randomBytes)).Replace("-", "")

$viewChecks = $views | ForEach-Object {
    "SELECT COUNT(*) FROM information_schema.VIEWS " +
    "WHERE TABLE_SCHEMA='$database' AND TABLE_NAME='$_';"
}
foreach ($statement in $viewChecks) {
    $count = & $mysql --protocol=tcp --host=$hostName --port=3306 `
        --user=root --batch --skip-column-names --execute=$statement
    if ($LASTEXITCODE -ne 0 -or $count -ne "1") {
        throw "View integrasi belum lengkap. Hubungi tim pengembang."
    }
}

$statements = @(
    "CREATE USER IF NOT EXISTS '$username'@'$hostName' IDENTIFIED BY '$password';",
    "ALTER USER '$username'@'$hostName' IDENTIFIED BY '$password';"
)
foreach ($view in $views) {
    $statements += "GRANT SELECT ON ``$database``.``$view`` TO '$username'@'$hostName';"
}
foreach ($statement in $statements) {
    & $mysql --protocol=tcp --host=$hostName --port=3306 `
        --user=root --execute=$statement
    if ($LASTEXITCODE -ne 0) {
        throw "Gagal menyiapkan akun read-only."
    }
}

[Environment]::SetEnvironmentVariable(
    "EMSS_KHANZA_PASSWORD", $password, "User"
)
$env:EMSS_KHANZA_PASSWORD = $password

foreach ($view in $views) {
    & $mysql --protocol=tcp --host=$hostName --port=3306 `
        --user=$username --password=$password --database=$database `
        --execute="SELECT 1 FROM ``$view`` LIMIT 1;" | Out-Null
    if ($LASTEXITCODE -ne 0) {
        throw "Akun read-only gagal membaca view integrasi."
    }
}

Write-Host ""
Write-Host "BERHASIL: akun read-only dan environment e-MSS sudah siap." `
    -ForegroundColor Green
Write-Host "Password dibuat otomatis dan tidak ditampilkan atau disimpan di source."
Write-Host "Tutup e-MSS bila masih terbuka, lalu jalankan run_mysql_local.bat."

