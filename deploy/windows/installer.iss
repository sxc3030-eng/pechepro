; Inno Setup 6.x script for Pechepro v0.1
; Builds dist\pechepro-setup.exe from dist\pechepro.exe (produced by PyInstaller).
; No admin rights required - installs into the user-profile Program Files area.
; Bilingual installer (English + French) per spec section 3.6.

[Setup]
AppId={{DEC96569-0C4A-45C7-8628-9AC4F230F15B}
AppName=Pechepro
AppVersion=0.1.0
AppPublisher=Master / sxc3030-eng
AppPublisherURL=https://github.com/sxc3030-eng/pechepro
DefaultDirName={userpf}\pechepro
DefaultGroupName=Pechepro
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputBaseFilename=pechepro-setup
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
LicenseFile=..\..\LICENSE
OutputDir=..\..\dist
SetupIconFile=..\..\app\static\img\logo.ico
UninstallDisplayName=Pechepro 0.1.0
UninstallDisplayIcon={app}\pechepro.exe

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"
Name: "french"; MessagesFile: "compiler:Languages\French.isl"

[Tasks]
Name: "desktopicon"; Description: "Creer un raccourci sur le Bureau / Create a desktop shortcut"; GroupDescription: "Raccourcis / Shortcuts:"

[Files]
Source: "..\..\dist\pechepro.exe"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\Pechepro"; Filename: "{app}\pechepro.exe"
Name: "{group}\{cm:UninstallProgram,Pechepro}"; Filename: "{uninstallexe}"
Name: "{userdesktop}\Pechepro"; Filename: "{app}\pechepro.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\pechepro.exe"; Description: "Lancer Pechepro / Launch Pechepro"; Flags: nowait postinstall skipifsilent
