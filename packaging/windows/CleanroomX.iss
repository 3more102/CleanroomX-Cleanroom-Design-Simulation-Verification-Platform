#ifndef MyAppVersion
  #define MyAppVersion "0.103.0.dev0"
#endif

#ifndef MyOutputBaseFilename
  #define MyOutputBaseFilename "CleanroomX-Setup-x64"
#endif

[Setup]
AppId={{8F32C7AA-9A76-4C56-82EE-CE29DA3587E1}
AppName=CleanroomX
AppVersion={#MyAppVersion}
AppPublisher=CleanroomX contributors
DefaultDirName={localappdata}\Programs\CleanroomX
DefaultGroupName=CleanroomX
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=..\..\dist\windows-installer
OutputBaseFilename={#MyOutputBaseFilename}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
SetupIconFile=..\..\build\pyinstaller\CleanroomX.ico
UninstallDisplayIcon={app}\CleanroomX.exe
CloseApplications=yes
RestartApplications=no
UsePreviousAppDir=yes
UsePreviousGroup=yes
SetupLogging=yes
VersionInfoCompany=CleanroomX contributors
VersionInfoDescription=CleanroomX Engineering Workstation Installer
VersionInfoProductName=CleanroomX
VersionInfoProductVersion={#MyAppVersion}

[Files]
Source: "..\..\dist\windows-standalone\CleanroomX\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\CleanroomX"; Filename: "{app}\CleanroomX.exe"; WorkingDir: "{app}"

[Run]
Filename: "{app}\CleanroomX.exe"; Description: "Launch CleanroomX"; Flags: nowait postinstall skipifsilent
