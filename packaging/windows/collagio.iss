; Windows installer for Collagio (Inno Setup 6).
;   iscc /DAppVersion=0.1.0 packaging\windows\collagio.iss
; Expects the PyInstaller folder at build\dist\Collagio; writes build\installer\.

#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif
#define SourceDir "..\..\build\dist\Collagio"

[Setup]
AppId={{6A7C3E52-8D41-4F0B-9B2E-1C5D7A3F9E64}
AppName=Collagio
AppVersion={#AppVersion}
AppPublisher=Markus Gamperle
AppPublisherURL=https://github.com/Gamperle/Collagio
AppSupportURL=https://github.com/Gamperle/Collagio/issues
DefaultDirName={autopf}\Collagio
DefaultGroupName=Collagio
DisableProgramGroupPage=yes
LicenseFile=..\..\LICENSE
OutputDir=..\..\build\installer
OutputBaseFilename=Collagio-{#AppVersion}-setup
SetupIconFile=..\icons\collagio.ico
UninstallDisplayIcon={app}\collagio-gui.exe
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
ChangesAssociations=yes
; Install for the current user without admin rights, or for everyone.
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"
Name: "german"; MessagesFile: "compiler:Languages\German.isl"

[CustomMessages]
english.AssociateFiles=Open .collagio projects with Collagio
german.AssociateFiles=.collagio-Projekte mit Collagio öffnen
english.ProjectType=Collagio project
german.ProjectType=Collagio-Projekt

[Tasks]
Name: "association"; Description: "{cm:AssociateFiles}"
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
Source: "{#SourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\Collagio"; Filename: "{app}\collagio-gui.exe"
Name: "{group}\{cm:UninstallProgram,Collagio}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\Collagio"; Filename: "{app}\collagio-gui.exe"; Tasks: desktopicon

[Registry]
Root: HKA; Subkey: "Software\Classes\.collagio"; ValueType: string; ValueName: ""; ValueData: "Collagio.Project"; Flags: uninsdeletevalue; Tasks: association
Root: HKA; Subkey: "Software\Classes\Collagio.Project"; ValueType: string; ValueName: ""; ValueData: "{cm:ProjectType}"; Flags: uninsdeletekey; Tasks: association
Root: HKA; Subkey: "Software\Classes\Collagio.Project\DefaultIcon"; ValueType: string; ValueName: ""; ValueData: "{app}\collagio-gui.exe,0"; Tasks: association
Root: HKA; Subkey: "Software\Classes\Collagio.Project\shell\open\command"; ValueType: string; ValueName: ""; ValueData: """{app}\collagio-gui.exe"" ""%1"""; Tasks: association

[Run]
Filename: "{app}\collagio-gui.exe"; Description: "{cm:LaunchProgram,Collagio}"; Flags: nowait postinstall skipifsilent
