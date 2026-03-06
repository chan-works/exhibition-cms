; Inno Setup Script for Exhibition CMS
; https://jrsoftware.org/isinfo.php

#define MyAppName "Exhibition CMS"
#define MyAppVersion "1.0.0"
#define MyAppPublisher "Exhibition CMS"
#define MyAppExeName "ExhibitionCMS.exe"
#define MyAppDescription "전시장 통합 제어 시스템"

[Setup]
AppId={{A1B2C3D4-E5F6-7890-ABCD-EF1234567890}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} v{#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppComments={#MyAppDescription}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
AllowNoIcons=yes
OutputDir=Output
OutputBaseFilename=ExhibitionCMS-Setup-v{#MyAppVersion}
SetupIconFile=
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
WizardResizable=yes
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
UninstallDisplayName={#MyAppName}
UninstallDisplayIcon={app}\{#MyAppExeName}
MinVersion=10.0
ArchitecturesAllowed=x64
ArchitecturesInstallIn64BitMode=x64

; 설치 디렉토리 색상 (모던 스타일)
WizardImageFile=compiler:WizModernImage.bmp
WizardSmallImageFile=compiler:WizModernSmallImage.bmp

[Languages]
Name: "korean"; MessagesFile: "compiler:Languages\Korean.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[CustomMessages]
korean.AppIsRunning=Exhibition CMS가 실행 중입니다. 종료 후 다시 시도하세요.
english.AppIsRunning=Exhibition CMS is running. Please close it and try again.

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Files]
Source: "dist\ExhibitionCMS\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
; 단일 exe 방식일 경우:
; Source: "dist\ExhibitionCMS.exe"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\{cm:UninstallProgram,{#MyAppName}}"; Filename: "{uninstallexe}"
Name: "{commondesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; \
  Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; \
  Flags: nowait postinstall skipifsilent

[UninstallDelete]
Type: filesandordirs; Name: "{app}"

[Code]
function InitializeSetup(): Boolean;
var
  ResultCode: Integer;
begin
  Result := True;
  // Check if app is already running
  if CheckForMutexes('ExhibitionCMS_Mutex') then
  begin
    MsgBox(CustomMessage('AppIsRunning'), mbError, MB_OK);
    Result := False;
  end;
end;
