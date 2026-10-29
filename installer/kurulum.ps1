# Setup tarafından kurulumun sonunda çalıştırılır: Python paketlerini ve ffmpeg'i indirip kurar.
# Elle de çalıştırılabilir (onarım için):  powershell -ExecutionPolicy Bypass -File kurulum.ps1 -AppDir "<kurulum klasörü>"
param([Parameter(Mandatory = $true)][string]$AppDir)

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"   # Invoke-WebRequest'i çok hızlandırır
[Console]::OutputEncoding = [Text.Encoding]::UTF8
$Host.UI.RawUI.WindowTitle = "FindWallpaper kuruluyor..."
Start-Transcript -Path (Join-Path $AppDir "kurulum.log") -Force | Out-Null

$py = Join-Path $AppDir "python\python.exe"
$pipArgs = @("--no-warn-script-location", "--disable-pip-version-check")

function Step($n, $text) { Write-Host "`n[$n/4] $text" -ForegroundColor Cyan }
# Out-Host: pip çıktısı ekrana gitsin, fonksiyonun dönüş değerine karışmasın
function Pip { & $py -m pip install @args @pipArgs | Out-Host; return $LASTEXITCODE }

try {
    Step 1 "pip hazırlanıyor"
    & $py (Join-Path $AppDir "python\get-pip.py") @pipArgs | Out-Host
    if ($LASTEXITCODE) { throw "pip kurulamadı" }

    Step 2 "PyTorch kuruluyor (en büyük parça, internet hızına göre birkaç dakika sürebilir)"
    $index = "cpu"
    $smi = Get-Command nvidia-smi -ErrorAction SilentlyContinue
    if ($smi) {
        $out = (& $smi.Source 2>$null) | Out-String
        if ($out -match "CUDA (?:UMD )?Version:\s*([\d.]+)") {
            $v = [version]$Matches[1]
            if ($v -ge [version]"13.0") { $index = "cu130" }
            elseif ($v -ge [version]"12.8") { $index = "cu128" }
            elseif ($v -ge [version]"12.6") { $index = "cu126" }
        }
    }
    Write-Host "Ekran kartı için seçilen sürüm: $index"
    $code = Pip torch torchvision --index-url "https://download.pytorch.org/whl/$index"
    if ($code -and $index -ne "cpu") {
        Write-Host "GPU sürümü kurulamadı, CPU sürümü deneniyor..." -ForegroundColor Yellow
        $code = Pip torch torchvision --index-url "https://download.pytorch.org/whl/cpu"
    }
    if ($code) { throw "PyTorch kurulamadı" }

    Step 3 "Diğer paketler kuruluyor"
    if (Pip -r (Join-Path $AppDir "app\requirements.txt")) { throw "Paketler kurulamadı" }

    Step 4 "ffmpeg kontrol ediliyor"
    $ffDir = Join-Path $AppDir "ffmpeg"
    if (Test-Path (Join-Path $ffDir "ffmpeg.exe")) {
        Write-Host "Zaten var."
    } else {
        $zip = Join-Path $env:TEMP "findwallpaper-ffmpeg.zip"
        $tmp = Join-Path $env:TEMP "findwallpaper-ffmpeg"
        Write-Host "İndiriliyor (gyan.dev, ~100 MB)..."
        Invoke-WebRequest "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip" -OutFile $zip -UseBasicParsing
        if (Test-Path $tmp) { Remove-Item $tmp -Recurse -Force }
        Expand-Archive $zip $tmp -Force
        New-Item -ItemType Directory -Force $ffDir | Out-Null
        foreach ($exe in "ffmpeg.exe", "ffprobe.exe") {
            $f = Get-ChildItem $tmp -Recurse -Filter $exe | Select-Object -First 1
            if (-not $f) { throw "$exe arşivde bulunamadı" }
            Copy-Item $f.FullName $ffDir -Force
        }
        Remove-Item $zip, $tmp -Recurse -Force -ErrorAction SilentlyContinue
    }

    Write-Host "`nKurulum tamamlandı." -ForegroundColor Green
    Stop-Transcript | Out-Null
    exit 0
}
catch {
    Write-Host "`nHATA: $_" -ForegroundColor Red
    Write-Host "Ayrıntılar: $(Join-Path $AppDir 'kurulum.log')"
    Stop-Transcript | Out-Null
    exit 1
}
