; HiCloud MP — Inno Setup installer script.
; Compiled by .github/workflows/windows-build.yml on version tags:
;   ISCC /DAppVersion=<x.y.z> packaging\HiCloudMP.iss
; Prerequisite: Nuitka standalone output present at ..\build\main.dist\

#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif

[Setup]
AppId={{7A1C6E3C-77B0-4A1F-9B4E-2C51B6A2D8F1}
AppName=HiCloud MP
AppVersion={#AppVersion}
AppPublisher=PhantomPixelDev
AppPublisherURL=https://github.com/PhantomPixelDev/HiCloudMP
DefaultDirName={autopf}\HiCloudMP
DefaultGroupName=HiCloud MP
DisableProgramGroupPage=yes
OutputDir=Output
OutputBaseFilename=HiCloudMP-Setup-{#AppVersion}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
ArchitecturesInstallIn64BitMode=x64compatible
UninstallDisplayIcon={app}\HiCloudMP.exe
SetupIconFile=..\icon.ico
PrivilegesRequiredOverridesAllowed=dialog

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Shortcuts:"; Flags: unchecked

[Files]
Source: "..\build\main.dist\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion

[Icons]
Name: "{group}\HiCloud MP"; Filename: "{app}\HiCloudMP.exe"
Name: "{autodesktop}\HiCloud MP"; Filename: "{app}\HiCloudMP.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\HiCloudMP.exe"; Description: "Launch HiCloud MP"; Flags: nowait postinstall skipifsilent

; No InstallDelete / UninstallDelete sections: upgrades overwrite binaries
; only; user data (settings, playlists, caches) lives in per-user app data
; and is never touched by install or uninstall.
