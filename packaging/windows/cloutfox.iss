; CloutFox setup. Built by packaging/build.py windows, which passes the defines.
#ifndef AppVersion
  #error Run through packaging/build.py windows
#endif

[Setup]
AppId={{4C454E73-FAE9-4B48-A408-F5C2F8427855}
AppName=CloutFox
AppVersion={#AppVersion}
AppVerName=CloutFox {#AppVersion}
AppPublisher=Cloutlab
AppPublisherURL=https://cloutlab.studio
AppSupportURL=https://github.com/cloutlab-studio/cloutfox/issues
AppUpdatesURL=https://github.com/cloutlab-studio/cloutfox/releases
AppCopyright=MIT License, Cloutlab
VersionInfoVersion={#AppVersion}
DefaultDirName={autopf}\CloutFox
DefaultGroupName=CloutFox
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
OutputDir={#OutputDir}
OutputBaseFilename=CloutFox-{#AppVersion}-setup-x64
SetupIconFile={#IconFile}
UninstallDisplayIcon={app}\CloutFox.exe
UninstallDisplayName=CloutFox
LicenseFile={#LicenseFile}
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
CloseApplications=yes
ShowLanguageDialog=auto

[Languages]
Name: "ru"; MessagesFile: "compiler:Languages\Russian.isl"
Name: "en"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[InstallDelete]
; A new version replaces the runtime and the code as a whole.
Type: filesandordirs; Name: "{app}\python"
Type: filesandordirs; Name: "{app}\app"

[Files]
Source: "{#SourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\CloutFox"; Filename: "{app}\CloutFox.exe"; AppUserModelID: "Cloutlab.CloutFox"
Name: "{autodesktop}\CloutFox"; Filename: "{app}\CloutFox.exe"; Tasks: desktopicon; AppUserModelID: "Cloutlab.CloutFox"

[Run]
Filename: "{app}\CloutFox.exe"; Description: "{cm:LaunchProgram,CloutFox}"; Flags: nowait postinstall skipifsilent
; An update started from CloutFox 3.1.2 runs this setup silently while the app is
; open: PrepareToInstall stops it, so start it again afterwards.
Filename: "{app}\CloutFox.exe"; Flags: nowait skipifnotsilent runasoriginaluser; Check: WasRunning

[UninstallDelete]
Type: filesandordirs; Name: "{app}\python"
Type: filesandordirs; Name: "{app}\app"

[Code]
var
  CloutFoxWasRunning: Boolean;

function WasRunning(): Boolean;
begin
  Result := CloutFoxWasRunning;
end;

{ Stops every process started from this install folder (the app, its browser
  runners, Playwright's node) and the Camoufox browsers using CloutFox's data
  folder, so no file is held while the new files are copied. Exit code 3 means
  something was running. }
function StopCloutFox(): Boolean;
var
  Script, Path: String;
  Code: Integer;
begin
  Result := False;
  Path := ExpandConstant('{tmp}\stop-cloutfox.ps1');
  Script :=
    'param([string]$App, [string]$Data)' + #13#10 +
    '$app = $App.TrimEnd([char]92) + [char]92' + #13#10 +
    '$data = $Data.TrimEnd([char]92) + [char]92' + #13#10 +
    '$found = Get-CimInstance Win32_Process | Where-Object {' + #13#10 +
    '  $_.ProcessId -ne $PID -and (' + #13#10 +
    '    ($_.ExecutablePath -and $_.ExecutablePath.StartsWith($app, [StringComparison]::OrdinalIgnoreCase)) -or' + #13#10 +
    '    ($_.Name -ieq "camoufox.exe" -and $_.CommandLine -and $_.CommandLine.IndexOf($data, [StringComparison]::OrdinalIgnoreCase) -ge 0))' + #13#10 +
    '}' + #13#10 +
    'if (-not $found) { exit 0 }' + #13#10 +
    '$found | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }' + #13#10 +
    'Start-Sleep -Seconds 2' + #13#10 +
    'exit 3' + #13#10;
  if not SaveStringToFile(Path, Script, False) then
    exit;
  if Exec('powershell.exe',
      '-NoProfile -NonInteractive -ExecutionPolicy Bypass -File "' + Path + '" -App "' +
      ExpandConstant('{app}') + '" -Data "' + ExpandConstant('{localappdata}\CloutFox') + '"',
      '', SW_HIDE, ewWaitUntilTerminated, Code) then
    Result := Code = 3;
end;

function PrepareToInstall(var NeedsRestart: Boolean): String;
begin
  Result := '';
  if DirExists(ExpandConstant('{app}')) then
    CloutFoxWasRunning := StopCloutFox();
end;

{ 3.1.2 starts every update with /CURRENTUSER, also from the MSI. On a copy
  installed for all users (this setup or the MSI, both in Program Files) that
  would put a second copy into the user's folder, so a silent per-user run
  steps back there: the old copy stays as it is, and its owner updates with the
  new setup or MSI by hand. }
function InitializeSetup(): Boolean;
begin
  Result := True;
  if WizardSilent and not IsAdminInstallMode and
     (RegKeyExists(HKEY_LOCAL_MACHINE_64,
        'Software\Microsoft\Windows\CurrentVersion\Uninstall\{4C454E73-FAE9-4B48-A408-F5C2F8427855}_is1') or
      FileExists(ExpandConstant('{commonpf64}\CloutFox\CloutFox.exe'))) then
  begin
    Log('CloutFox is installed for all users; a silent per-user update is skipped.');
    Result := False;
  end;
end;
