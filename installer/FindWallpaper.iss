; FindWallpaper kurulum sihirbazı (Inno Setup 6).  Derlemek için: installer\build.ps1

#ifndef AppVersion
  #define AppVersion "1.0.0"
#endif
#define AppName "FindWallpaper"
#define AppExe "FindWallpaper.exe"

[Setup]
AppId={{8A4E29D4-66BA-46BE-BB11-B7DFEC5573AB}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher={#AppName}
VersionInfoVersion={#AppVersion}
; kullanıcı klasörüne kurulur: yönetici izni gerekmez, modeller/çıktılar yazılabilir kalır
DefaultDirName={localappdata}\Programs\{#AppName}
PrivilegesRequired=lowest
DisableProgramGroupPage=yes
OutputDir=Output
OutputBaseFilename={#AppName}-Setup-{#AppVersion}
SetupIconFile=icon.ico
UninstallDisplayIcon={app}\{#AppExe}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible

[Languages]
Name: "turkish"; MessagesFile: "compiler:Languages\Turkish.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[CustomMessages]
turkish.Downloading=Gerekli paketler indiriliyor (PyTorch, YOLO, CLIP, ffmpeg). Açılan pencerede ilerlemeyi görebilirsin; internet hızına göre birkaç dakika sürebilir...
english.Downloading=Downloading required packages (PyTorch, YOLO, CLIP, ffmpeg). Progress is shown in the console window; this can take a few minutes...
turkish.SetupFailed=Paketlerin kurulumu tamamlanamadı. İnternet bağlantını kontrol edip kurulumu tekrar çalıştır.%n%nAyrıntılar: %1
english.SetupFailed=Installing the packages failed. Check your internet connection and run the setup again.%n%nDetails: %1
turkish.InternetNote=Kurulumun sonunda gerekli paketler internetten indirilecek (NVIDIA ekran kartı varsa ~3 GB, yoksa ~1 GB).
english.InternetNote=At the end of the setup the required packages are downloaded (~3 GB with an NVIDIA GPU, ~1 GB otherwise).

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Files]
Source: "build\{#AppExe}"; DestDir: "{app}"; Flags: ignoreversion
Source: "build\python\*"; DestDir: "{app}\python"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "kurulum.ps1"; DestDir: "{app}"; Flags: ignoreversion
Source: "icon.ico"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\app.py"; DestDir: "{app}\app"; Flags: ignoreversion
Source: "..\bul.py"; DestDir: "{app}\app"; Flags: ignoreversion
Source: "..\requirements.txt"; DestDir: "{app}\app"; Flags: ignoreversion
Source: "..\README.md"; DestDir: "{app}\app"; Flags: ignoreversion
Source: "..\wallpaper_finder\*.py"; DestDir: "{app}\app\wallpaper_finder"; Flags: ignoreversion

[Dirs]
Name: "{app}\app\modeller"

[Icons]
Name: "{autoprograms}\{#AppName}"; Filename: "{app}\{#AppExe}"; IconFilename: "{app}\icon.ico"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; IconFilename: "{app}\icon.ico"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExe}"; Description: "{cm:LaunchProgram,{#AppName}}"; Flags: postinstall nowait skipifsilent

[UninstallDelete]
; pip'in kurduğu paketler ve indirilen modeller kurulum kaydında olmadığından klasör tamamen silinir
Type: filesandordirs; Name: "{app}"

[Code]
procedure InitializeWizard;
begin
  WizardForm.WelcomeLabel2.Caption := WizardForm.WelcomeLabel2.Caption + #13#10#13#10 + CustomMessage('InternetNote');
end;

procedure CurStepChanged(CurStep: TSetupStep);
var
  rc: Integer;
  params: String;
begin
  if CurStep = ssPostInstall then
  begin
    WizardForm.StatusLabel.Caption := CustomMessage('Downloading');
    params := '-NoProfile -ExecutionPolicy Bypass -File "' + ExpandConstant('{app}\kurulum.ps1') +
              '" -AppDir "' + ExpandConstant('{app}') + '"';
    if (not Exec('powershell.exe', params, '', SW_SHOW, ewWaitUntilTerminated, rc)) or (rc <> 0) then
      MsgBox(FmtMessage(CustomMessage('SetupFailed'), [ExpandConstant('{app}\kurulum.log')]), mbError, MB_OK);
  end;
end;
