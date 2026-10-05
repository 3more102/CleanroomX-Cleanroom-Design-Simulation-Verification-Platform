#ifndef AppVersion
  #error AppVersion must be defined by the build pipeline
#endif
#ifndef SourceDir
  #error SourceDir must be defined by the build pipeline
#endif
#ifndef OutputDir
  #error OutputDir must be defined by the build pipeline
#endif
#ifndef OutputBaseFilename
  #define OutputBaseFilename "CleanroomX-Setup"
#endif

[Setup]
AppId={{8A609071-4521-4B60-B8D2-ACAD5BF53A72}
AppName=CleanroomX
AppVersion={#AppVersion}
AppVerName=CleanroomX {#AppVersion}
AppPublisher=CleanroomX contributors
AppComments=Cleanroom design, simulation, verification, evidence, and reporting workstation
DefaultDirName={localappdata}\Programs\CleanroomX
DefaultGroupName=CleanroomX
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir={#OutputDir}
OutputBaseFilename={#OutputBaseFilename}
SetupArchitecture=x64
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
SetupLogging=yes
CloseApplications=yes
RestartApplications=no
UninstallDisplayIcon={app}\CleanroomX.exe
UsePreviousAppDir=yes
VersionInfoProductName=CleanroomX
VersionInfoDescription=CleanroomX Windows Installer
VersionInfoCompany=CleanroomX contributors

[Files]
Source: "{#SourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\CleanroomX"; Filename: "{app}\CleanroomX.exe"
Name: "{autodesktop}\CleanroomX"; Filename: "{app}\CleanroomX.exe"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop shortcut"; GroupDescription: "Additional shortcuts:"; Flags: unchecked

[Run]
Filename: "{app}\CleanroomX.exe"; Description: "Launch CleanroomX"; Flags: nowait postinstall skipifsilent
