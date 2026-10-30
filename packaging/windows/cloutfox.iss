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

[UninstallDelete]
Type: filesandordirs; Name: "{app}\python"
Type: filesandordirs; Name: "{app}\app"
