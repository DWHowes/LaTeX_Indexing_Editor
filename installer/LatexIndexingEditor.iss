; Inno Setup script for LaTeX Indexing Editor (alpha distribution).
; Build with:
;   "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" installer\LatexIndexingEditor.iss
; Prerequisite: a fresh PyInstaller build must already exist at
;   dist\LatexIndexingEditor\  (see LatexIndexingEditor.spec)

#define MyAppName "LaTeX Indexing Editor"
#define MyAppVersion "0.1.0-alpha"
#define MyAppPublisher "DH Indexing"
#define MyAppExeName "LatexIndexingEditor.exe"
#define MySourceDir "..\dist\LatexIndexingEditor"

[Setup]
; Fixed AppId -- keep this stable across versions so upgrades replace
; the previous install cleanly instead of side-by-side installing.
AppId={{4567C3EA-2541-4270-9E8D-1B76098A6AAD}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
; Per-user install under %LOCALAPPDATA%\Programs -- no admin rights
; required, sidesteps Program Files write-permission issues (the app
; keeps a writable VIAF lookup cache at data\name_cache.db, next to the
; executable, which would fail under a real Program Files install run
; by a non-admin alpha tester).
DefaultDirName={autopf}\{#MyAppName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir=..\dist_installer
OutputBaseFilename=LatexIndexingEditor-Setup-{#MyAppVersion}
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
UninstallDisplayIcon={app}\{#MyAppExeName}
ArchitecturesInstallIn64BitMode=x64

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop shortcut"; GroupDescription: "Additional shortcuts:"; Flags: unchecked

[Files]
Source: "{#MySourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon
Name: "{autoprograms}\Uninstall {#MyAppName}"; Filename: "{uninstallexe}"

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Launch {#MyAppName}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
; The app writes a VIAF lookup cache (data\name_cache.db) and other
; runtime state next to the executable -- clean those up on uninstall
; along with the files Inno tracked from [Files].
Type: filesandordirs; Name: "{app}\data"
