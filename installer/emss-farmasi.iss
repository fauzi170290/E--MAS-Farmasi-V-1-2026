#define MyAppName "E-MAS Farmasi"
#define MyAppVersion "1.0.1"
#define MyAppPublisher "Tim E-MAS Farmasi"
#define MyAppExeName "E-MAS Farmasi.exe"
#ifndef AppDistDir
  #define AppDistDir "..\dist\E-MAS Farmasi"
#endif

[Setup]
AppId={{A532C224-9E26-4A08-90B6-84D7A9BB40B5}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\eMSS Farmasi RS
DefaultGroupName={#MyAppName}
UsePreviousGroup=no
DisableProgramGroupPage=yes
PrivilegesRequired=admin
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=..\outputs\installer
OutputBaseFilename=E-MAS-Farmasi-Setup-{#MyAppVersion}-x64
SetupIconFile=..\src\emss\assets\emss.ico
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
UninstallDisplayIcon={app}\{#MyAppExeName}
CloseApplications=yes
RestartApplications=no

[Tasks]
Name: "desktopicon"; Description: "Buat ikon di Desktop"; GroupDescription: "Ikon tambahan:"
Name: "startup"; Description: "Jalankan otomatis saat pengguna masuk Windows"; GroupDescription: "Startup:"; Flags: unchecked

[Dirs]
Name: "{commonappdata}\eMSSFarmasi"; Permissions: users-modify
Name: "{commonappdata}\eMSSFarmasi\Database"; Permissions: users-modify
Name: "{commonappdata}\eMSSFarmasi\Backups"; Permissions: users-modify
Name: "{commonappdata}\eMSSFarmasi\Exports"; Permissions: users-modify
Name: "{commonappdata}\eMSSFarmasi\Logs"; Permissions: users-modify

[Files]
Source: "{#AppDistDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "config.production.toml"; DestDir: "{commonappdata}\eMSSFarmasi"; DestName: "config.toml"; Flags: onlyifdoesntexist uninsneveruninstall

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Parameters: "--config ""{commonappdata}\eMSSFarmasi\config.toml"" gui"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Parameters: "--config ""{commonappdata}\eMSSFarmasi\config.toml"" gui"; Tasks: desktopicon
Name: "{userstartup}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Parameters: "--config ""{commonappdata}\eMSSFarmasi\config.toml"" gui"; Tasks: startup

[Run]
Filename: "{app}\{#MyAppExeName}"; Parameters: "--config ""{commonappdata}\eMSSFarmasi\config.toml"" gui"; Description: "Jalankan {#MyAppName}"; Flags: nowait postinstall skipifsilent; Check: CanLaunchApplication

[UninstallDelete]
; Data di ProgramData sengaja tidak dihapus agar database dan backup tetap dapat dipulihkan.

[InstallDelete]
; Remove only known obsolete application shortcuts. The legacy executable remains a compatibility alias.
Type: files; Name: "{autodesktop}\e-MSS Farmasi — DDI Checker.lnk"
Type: files; Name: "{autodesktop}\e-MSS Farmasi RS.lnk"
Type: files; Name: "{autoprograms}\e-MSS Farmasi — DDI Checker\e-MSS Farmasi — DDI Checker.lnk"
Type: files; Name: "{autoprograms}\e-MSS Farmasi RS\e-MSS Farmasi RS.lnk"

[Code]
const
  BadIcuHash = '2882afacabd9d901762ab196c7a319b03051af39291e47fef51fcb69c26ab5b8';

function CanLaunchApplication: Boolean;
begin
  Result := True;
end;

function PrepareToInstall(var NeedsRestart: Boolean): String;
var
  IcuPath, BackupPath: String;
begin
  Result := '';
  IcuPath := ExpandConstant('{app}\icuuc.dll');
  BackupPath := IcuPath + '.quarantined-0.31.0';
  if not FileExists(IcuPath) then Exit;
  if CompareText(GetSHA256OfFile(IcuPath), BadIcuHash) <> 0 then
  begin
    Result := 'Ditemukan icuuc.dll yang tidak dikenal. File tidak diubah. Hubungi dukungan e-MSS.';
    Exit;
  end;
  if FileExists(BackupPath) then
  begin
    Result := 'File karantina ICU sudah ada. Tidak ada file yang ditimpa. Hubungi dukungan e-MSS.';
    Exit;
  end;
  if not RenameFile(IcuPath, BackupPath) then
    Result := 'Tutup e-MSS dan jendela error, lalu ulangi instalasi. DLL ICU belum dapat dikarantina.';
end;

procedure CurStepChanged(CurStep: TSetupStep);
var OldLink, NewLink: String;
begin
  if CurStep <> ssPostInstall then Exit;
  OldLink := ExpandConstant('{userstartup}\e-MSS Farmasi — DDI Checker.lnk');
  if not FileExists(OldLink) then
    OldLink := ExpandConstant('{userstartup}\e-MSS Farmasi RS.lnk');
  if FileExists(OldLink) then
  begin
    NewLink := ExpandConstant('{userstartup}\E-MAS Farmasi.lnk');
    CreateShellLink(NewLink, 'E-MAS Farmasi', ExpandConstant('{app}\{#MyAppExeName}'),
      ExpandConstant('--config "{commonappdata}\eMSSFarmasi\config.toml" gui'),
      ExpandConstant('{app}'), ExpandConstant('{app}\{#MyAppExeName}'), 0, SW_SHOWNORMAL);
    if FileExists(NewLink) then DeleteFile(OldLink);
  end;
end;
