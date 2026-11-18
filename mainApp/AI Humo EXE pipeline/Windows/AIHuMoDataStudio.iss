#ifndef MyAppVersion
  #define MyAppVersion "0.5.0"
#endif

#define MyAppName "AIHuMo Data Studio"
#define MyAppPublisher "AIHuMo"
#define MyAppExeName "AIHuMo Data Studio.exe"

[Setup]
AppId={{6EFC976F-316D-4F7D-A05E-A8C5B2CE5C31}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\AIHuMo Data Studio
DefaultGroupName=AIHuMo Data Studio
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
OutputDir=..\release
OutputBaseFilename=AIHuMo-Data-Studio-Windows-x64-Setup-v{#MyAppVersion}
SetupIconFile=..\..\assets\app_branding\aihumo_logo_v5.ico
UninstallDisplayIcon={app}\{#MyAppExeName}
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
CloseApplications=yes
RestartApplications=no
VersionInfoVersion={#MyAppVersion}
VersionInfoCompany={#MyAppPublisher}
VersionInfoDescription=AIHuMo movement processing, annotation, visualization, and games
VersionInfoProductName={#MyAppName}

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Shortcuts:"; Flags: unchecked

[Files]
Source: "..\dist\v{#MyAppVersion}\AIHuMo Data Studio\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\AIHuMo Data Studio"; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\AIHuMo Data Studio"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Launch AIHuMo Data Studio"; Flags: nowait postinstall skipifsilent

[Code]
var
  ProfilePage: TInputQueryWizardPage;
  CameraPage: TInputOptionWizardPage;
  FolderPage: TInputDirWizardPage;
  StarterPage: TInputFileWizardPage;
  PrivacyPage: TInputOptionWizardPage;

function JsonEscape(Value: String): String;
begin
  StringChangeEx(Value, '\', '\\', True);
  StringChangeEx(Value, '"', '\"', True);
  StringChangeEx(Value, #13#10, '\n', True);
  StringChangeEx(Value, #10, '\n', True);
  Result := Value;
end;

function JsonString(Value: String): String;
begin
  Result := '"' + JsonEscape(Value) + '"';
end;

procedure InitializeWizard;
begin
  ProfilePage := CreateInputQueryPage(wpSelectTasks,
    'Your AIHuMo workspace',
    'Set defaults for the first launch',
    'These values stay on this computer and can be changed later in Settings.');
  ProfilePage.Add('Participant or user name (optional):', False);
  ProfilePage.Add('Default camera name:', False);
  ProfilePage.Values[1] := 'camera_01';

  CameraPage := CreateInputOptionPage(ProfilePage.ID,
    'Preferred camera view',
    'Choose the view used as the initial annotation default',
    'Choose one option. Three-quarter represents the view between front and side.', True, False);
  CameraPage.Add('Front');
  CameraPage.Add('Side');
  CameraPage.Add('Rear');
  CameraPage.Add('Three-quarter');
  CameraPage.Add('N/A / unknown');
  CameraPage.SelectedValueIndex := 0;

  FolderPage := CreateInputDirPage(CameraPage.ID,
    'Default AIHuMo folders',
    'Choose where file pickers should begin',
    'The installer does not copy your recordings. These folders only become defaults.',
    False, 'AIHuMo');
  FolderPage.Add('Source videos:');
  FolderPage.Add('Skeleton videos:');
  FolderPage.Add('Feature Parquet files:');
  FolderPage.Add('Annotation JSON files:');
  FolderPage.Add('New processed outputs:');
  FolderPage.Values[0] := ExpandConstant('{userdocs}\AIHuMo\Videos');
  FolderPage.Values[1] := ExpandConstant('{userdocs}\AIHuMo\Skeletons');
  FolderPage.Values[2] := ExpandConstant('{userdocs}\AIHuMo\Features');
  FolderPage.Values[3] := ExpandConstant('{userdocs}\AIHuMo\Annotations');
  FolderPage.Values[4] := ExpandConstant('{userdocs}\AIHuMo\Processed');

  StarterPage := CreateInputFilePage(FolderPage.ID,
    'Optional starter recording',
    'Choose files to review when AIHuMo first opens',
    'A raw video opens Mode 0. A matching skeleton video and feature Parquet open Mode 1. You can add more videos in the app setup screen.');
  StarterPage.Add('Source or primary video:', 'Video files|*.mp4;*.mov;*.avi;*.mkv;*.webm|All files|*.*', '.mp4');
  StarterPage.Add('Matching skeleton video (optional):', 'Video files|*.mp4;*.mov;*.avi;*.mkv;*.webm|All files|*.*', '.mp4');
  StarterPage.Add('Matching feature Parquet (optional):', 'Parquet files|*.parquet|All files|*.*', '.parquet');
  StarterPage.Add('Matching annotation JSON (optional):', 'JSON files|*.json|All files|*.*', '.json');

  PrivacyPage := CreateInputOptionPage(StarterPage.ID,
    'Local data and permissions',
    'Confirm how AIHuMo handles your selected files',
    'AIHuMo processes locally by default. The installer never uploads, deletes, or moves original recordings.', False, False);
  PrivacyPage.Add('I understand that selected recordings remain in their original locations.');
  PrivacyPage.Values[0] := True;
end;

function NextButtonClick(CurPageID: Integer): Boolean;
begin
  Result := True;
  if (CurPageID = PrivacyPage.ID) and (not PrivacyPage.Values[0]) then
  begin
    MsgBox('Confirm the local-file notice before continuing.', mbInformation, MB_OK);
    Result := False;
  end;
end;

procedure WriteBootstrapPlan;
var
  StateDir, Path, CameraAngle, StarterArray, Json: String;
begin
  case CameraPage.SelectedValueIndex of
    0: CameraAngle := 'Front';
    1: CameraAngle := 'Side';
    2: CameraAngle := 'Rear';
    3: CameraAngle := 'Three-quarter';
  else
    CameraAngle := 'N/A';
  end;
  if StarterPage.Values[0] <> '' then
    StarterArray := '[' + JsonString(StarterPage.Values[0]) + ']'
  else
    StarterArray := '[]';
  Json := '{' + #13#10 +
    '  "schema_version": 1,' + #13#10 +
    '  "participant": ' + JsonString(ProfilePage.Values[0]) + ',' + #13#10 +
    '  "camera_name": ' + JsonString(ProfilePage.Values[1]) + ',' + #13#10 +
    '  "camera_angle": ' + JsonString(CameraAngle) + ',' + #13#10 +
    '  "source_directory": ' + JsonString(FolderPage.Values[0]) + ',' + #13#10 +
    '  "skeleton_directory": ' + JsonString(FolderPage.Values[1]) + ',' + #13#10 +
    '  "features_directory": ' + JsonString(FolderPage.Values[2]) + ',' + #13#10 +
    '  "annotations_directory": ' + JsonString(FolderPage.Values[3]) + ',' + #13#10 +
    '  "output_directory": ' + JsonString(FolderPage.Values[4]) + ',' + #13#10 +
    '  "starter_video": ' + JsonString(StarterPage.Values[0]) + ',' + #13#10 +
    '  "starter_videos": ' + StarterArray + ',' + #13#10 +
    '  "starter_skeleton": ' + JsonString(StarterPage.Values[1]) + ',' + #13#10 +
    '  "starter_features": ' + JsonString(StarterPage.Values[2]) + ',' + #13#10 +
    '  "starter_annotations": ' + JsonString(StarterPage.Values[3]) + #13#10 +
    '}' + #13#10;
  StateDir := ExpandConstant('{localappdata}\AIHuMo');
  ForceDirectories(StateDir);
  Path := StateDir + '\installer-bootstrap.json';
  if not SaveStringToFile(Path, Json, False) then
    MsgBox('AIHuMo was installed, but the first-launch setup plan could not be saved.', mbError, MB_OK);
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssPostInstall then
    WriteBootstrapPlan;
end;
