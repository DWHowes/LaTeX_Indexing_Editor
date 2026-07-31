; Inno Setup script for LaTeX Indexing Editor (alpha distribution).
; Build with:
;   "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" installer\LatexIndexingEditor.iss
; Prerequisite: a fresh PyInstaller build must already exist at
;   dist\LatexIndexingEditor\  (see LatexIndexingEditor.spec)

#define MyAppName "LaTeX Indexing Editor"
; Keep in step with APP_VERSION in models/app_version.py, which is what the
; About box reports -- Inno cannot read the Python module.
#define MyAppVersion "0.2.0-alpha"
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
; The installer's own icon. The uninstall entry points at the exe, which
; carries the same icon embedded by PyInstaller.
SetupIconFile=..\icons\lidx.ico
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
; Session logs written before a project is opened land beside the exe.
; The folder used to be hidden ('.session_logs'); it is now visible and
; user-configurable (Preferences > General), so leaving it behind after an
; uninstall would be conspicuous. Both names are removed, since an install
; upgraded from an earlier version can have the old one.
Type: filesandordirs; Name: "{app}\session_logs"
Type: filesandordirs; Name: "{app}\.session_logs"
