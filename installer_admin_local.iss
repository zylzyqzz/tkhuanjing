#define MyAppName "TK 管理后台（本地版）"
#define MyAppVersion "2.10.0"

[Setup]
AppId={{DF5D0A8C-071A-4F2D-8708-1EF46C12CA25}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher=维度光年
DefaultDirName={localappdata}\Programs\WeiDuTKAdminLocal
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir=dist_admin_setup
OutputBaseFilename=TK管理后台本地安装程序-2.4.0
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
SetupIconFile=assets\app_icon.ico
UninstallDisplayName={#MyAppName}
UninstallDisplayIcon={app}\TKAdminLocal.exe
CloseApplications=yes
ArchitecturesAllowed=x64compatible

[Dirs]
Name: "{app}\runtime"

[Files]
Source: "dist_admin_local\TKAdminLocal\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "runtime\platform.sqlite3"; DestDir: "{app}\runtime"; Flags: onlyifdoesntexist uninsneveruninstall

[Icons]
Name: "{autodesktop}\启动 TK 管理后台"; Filename: "{app}\TKAdminLocal.exe"; WorkingDir: "{app}"; IconFilename: "{app}\TKAdminLocal.exe"
Name: "{autodesktop}\停止 TK 管理后台"; Filename: "{app}\TKAdminLocal.exe"; Parameters: "--stop"; WorkingDir: "{app}"; IconFilename: "{app}\TKAdminLocal.exe"
Name: "{group}\启动 TK 管理后台"; Filename: "{app}\TKAdminLocal.exe"; WorkingDir: "{app}"
Name: "{group}\停止 TK 管理后台"; Filename: "{app}\TKAdminLocal.exe"; Parameters: "--stop"; WorkingDir: "{app}"
