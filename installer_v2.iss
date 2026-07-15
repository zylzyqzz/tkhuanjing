#define MyAppName "维度 TikTok 直播开播助手"
#define MyAppVersion "2.0.0"
#define MyAppExeName "TKLiveCheck.exe"

[Setup]
AppId={{0BE3AF73-ABCF-4D45-A35B-86D798960D74}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher=维度光年
DefaultDirName={localappdata}\Programs\WeiDuTKLiveCheck
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir=dist_setup
OutputBaseFilename=维度TikTok直播开播助手安装程序-2.0.0
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
SetupIconFile=assets\app_icon.ico
UninstallDisplayName={#MyAppName}
UninstallDisplayIcon={app}\app_icon.ico
CloseApplications=yes
RestartApplications=yes
ArchitecturesAllowed=x64compatible

[Files]
Source: "dist_client\TKLiveCheck.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "dist_updater\TKUpdater.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "assets\收款码.jpg"; DestDir: "{app}"; Flags: ignoreversion
Source: "assets\客服二维码.png"; DestDir: "{app}"; Flags: ignoreversion
Source: "assets\app_icon.ico"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"; IconFilename: "{app}\app_icon.ico"
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"; IconFilename: "{app}\app_icon.ico"

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "启动{#MyAppName}"; Flags: nowait postinstall skipifsilent
