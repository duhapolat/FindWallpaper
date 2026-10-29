# Kurulum dosyasını üretir:  powershell -ExecutionPolicy Bypass -File installer\build.ps1 [-Version 1.0.0]
# Çıktı: installer\Output\FindWallpaper-Setup-<sürüm>.exe
# Gerekenler: Inno Setup 6 (winget install JRSoftware.InnoSetup) ve Windows'ta hazır gelen .NET Framework 4.
param([string]$Version = "1.0.0")

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"
$here = $PSScriptRoot
$build = Join-Path $here "build"
$pyVer = "3.12.10"   # gömülü Python (python.org "embeddable package")

New-Item -ItemType Directory -Force $build | Out-Null

# 1) Gömülü Python
$pyDir = Join-Path $build "python"
if (-not (Test-Path (Join-Path $pyDir "python.exe"))) {
    Write-Host "Gömülü Python $pyVer indiriliyor..."
    $zip = Join-Path $build "python-embed.zip"
    Invoke-WebRequest "https://www.python.org/ftp/python/$pyVer/python-$pyVer-embed-amd64.zip" -OutFile $zip -UseBasicParsing
    Expand-Archive $zip $pyDir -Force
    Remove-Item $zip
}
# site-packages'ı ve uygulama klasörünü (..\app) içe aktarma yoluna ekle
$pth = Get-ChildItem $pyDir -Filter "python*._pth" | Select-Object -First 1
$zipName = (Get-ChildItem $pyDir -Filter "python*.zip" | Select-Object -First 1).Name
Set-Content $pth.FullName -Encoding ascii -Value @($zipName, ".", "..\app", "import site")
if (-not (Test-Path (Join-Path $pyDir "get-pip.py"))) {
    Write-Host "get-pip.py indiriliyor..."
    Invoke-WebRequest "https://bootstrap.pypa.io/get-pip.py" -OutFile (Join-Path $pyDir "get-pip.py") -UseBasicParsing
}

# 2) Başlatıcı exe
Write-Host "FindWallpaper.exe derleniyor..."
$csc = Join-Path $env:WINDIR "Microsoft.NET\Framework64\v4.0.30319\csc.exe"
& $csc /nologo /target:exe /codepage:65001 /optimize+ "/win32icon:$here\icon.ico" /r:System.Windows.Forms.dll `
    "/out:$build\FindWallpaper.exe" "$here\launcher.cs"
if ($LASTEXITCODE) { throw "csc başarısız" }

# 3) Kurulum dosyası
$iscc = @("$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe", "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
          "$env:ProgramFiles\Inno Setup 6\ISCC.exe") | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $iscc) { throw "Inno Setup 6 bulunamadı: winget install JRSoftware.InnoSetup" }
Write-Host "Kurulum dosyası oluşturuluyor..."
& $iscc /Q "/DAppVersion=$Version" (Join-Path $here "FindWallpaper.iss")
if ($LASTEXITCODE) { throw "ISCC başarısız" }

$out = Join-Path $here "Output\FindWallpaper-Setup-$Version.exe"
Write-Host ("Hazır: {0} ({1:N1} MB)" -f $out, ((Get-Item $out).Length / 1MB)) -ForegroundColor Green
