#define MyAppName "VD 开播助手"
#define MyAppVersion "2.1.0"
#define MyAppExeName "VDLiveCheck.exe"

[Setup]
AppId={{0BE3AF73-ABCF-4D45-A35B-86D798960D74}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher=VD 开播助手
DefaultDirName={localappdata}\Programs\VDLiveCheck
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir=dist_setup_v2
OutputBaseFilename=VD开播助手安装程序-2.1.0
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
SetupIconFile=assets\app_icon.ico
UninstallDisplayName={#MyAppName}
UninstallDisplayIcon={app}\{#MyAppExeName}
CloseApplications=yes
RestartApplications=yes
ArchitecturesAllowed=x64compatible
VersionInfoVersion=2.1.0.0
VersionInfoProductName={#MyAppName}
VersionInfoCompany=VD 开播助手

[Files]
Source: "dist_client_v2\VDLiveCheck\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "dist_updater_v2\TKUpdater.exe"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"; IconFilename: "{app}\{#MyAppExeName}"
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"; IconFilename: "{app}\{#MyAppExeName}"

[Tasks]
Name: "desktopicon"; Description: "创建桌面快捷方式"; GroupDescription: "快捷方式："; Flags: checkedonce

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "启动 {#MyAppName}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
Type: filesandordirs; Name: "{app}\_internal"
