#define MyAppName "Liquidated Subtitle Studio"
#ifndef MyAppVersion
  #define MyAppVersion "1.0.0"
#endif
#define MyAppPublisher "liquidated"
#define MyAppExeName "LiquidatedSubtitleStudio.exe"
#define MyAppId "{{D7D05631-79C2-4A63-A1D1-9787896D8F4F}"
#define MyOutputBaseFilename "LiquidatedSubtitleStudioSetup"

[Setup]
AppId={#MyAppId}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppCopyright={#MyAppPublisher}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
PrivilegesRequired=admin
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
UninstallDisplayIcon={app}\{#MyAppExeName}
SetupIconFile=icon\icon.ico
OutputDir=dist\installer
OutputBaseFilename={#MyOutputBaseFilename}
WizardImageFile=installer-assets\wizard.png
WizardSmallImageFile=installer-assets\wizard-small.png
VersionInfoVersion={#MyAppVersion}
VersionInfoCompany={#MyAppPublisher}
VersionInfoDescription={#MyAppName} Installer
VersionInfoCopyright={#MyAppPublisher}
VersionInfoTextVersion={#MyAppVersion}
VersionInfoProductName={#MyAppName}
VersionInfoProductVersion={#MyAppVersion}
VersionInfoProductTextVersion={#MyAppVersion}

[Languages]
Name: "russian"; MessagesFile: "compiler:Languages\Russian.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; Flags: unchecked

[Files]
Source: "dist\LiquidatedSubtitleStudio\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Parameters: "--prepare-runtime"; StatusMsg: "Подготавливаются модели распознавания и runtime-файлы..."; Flags: runhidden waituntilterminated
Filename: "{app}\{#MyAppExeName}"; Description: "Запустить {#MyAppName}"; Flags: nowait postinstall skipifsilent
