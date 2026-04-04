; ============================================================
; FileTools Inno Setup Script
; 配合 Nuitka 构建生成 Windows 安装包
; ============================================================

#define MyAppName "FileTools"
#define MyAppVersion "1.1.0"
#define MyAppPublisher "FileTools"
#define MyAppURL "https://github.com/Dry-U/File-tools"
#define MyAppExeName "main.exe"
#define MyAppId "{{A1B2C3D4-E5F6-7890-ABCD-EF1234567890}}"

[Setup]
; 应用基本信息
AppId={#MyAppId}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppURL}

; 安装目录
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes

; 权限
PrivilegesRequired=admin
PrivilegesRequiredOverridesAllowed=dialog

; 输出
OutputDir=..\dist\installer
OutputBaseFilename=FileTools-{#MyAppVersion}-win64-setup
SetupIconFile=..\frontend\static\logo.ico
UninstallDisplayIcon={app}\{#MyAppExeName}

; 压缩
Compression=lzma2/ultra64
SolidCompression=yes
LZMAUseSeparateProcess=yes
LZMANumBlockThreads=4

; 界面
WizardStyle=modern
WizardSizePercent=100

; 64位 Windows
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible

; 版本信息
VersionInfoVersion={#MyAppVersion}
VersionInfoCompany={#MyAppPublisher}
VersionInfoDescription=智能文件检索与问答系统
VersionInfoProductName={#MyAppName}
VersionInfoProductVersion={#MyAppVersion}

[Languages]
Name: "chinesesimplified"; MessagesFile: "compiler:Languages\ChineseSimplified.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked
Name: "fileassochk"; Description: "关联常用文件格式 (.txt, .pdf, .docx)"; GroupDescription: "文件关联:"

[Files]
; 主程序目录 (Nuitka onedir 模式输出到 main.dist)
Source: "..\dist\main.dist\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\{cm:UninstallProgram,{#MyAppName}}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Registry]
; 文件关联 - txt
Root: HKCR; Subkey: ".txt"; ValueType: string; ValueName: ""; ValueData: "FileTools.txt"; Flags: uninsdeletevalue; Tasks: fileassochk
Root: HKCR; Subkey: "FileTools.txt"; ValueType: string; ValueName: ""; ValueData: "文本文档"; Flags: uninsdeletekey; Tasks: fileassochk
Root: HKCR; Subkey: "FileTools.txt\shell\open\command"; ValueType: string; ValueName: ""; ValueData: """{app}\{#MyAppExeName}"" ""%1"""; Tasks: fileassochk

; 文件关联 - pdf
Root: HKCR; Subkey: ".pdf"; ValueType: string; ValueName: ""; ValueData: "FileTools.pdf"; Flags: uninsdeletevalue; Tasks: fileassochk
Root: HKCR; Subkey: "FileTools.pdf"; ValueType: string; ValueName: ""; ValueData: "PDF文档"; Flags: uninsdeletekey; Tasks: fileassochk
Root: HKCR; Subkey: "FileTools.pdf\shell\open\command"; ValueType: string; ValueName: ""; ValueData: """{app}\{#MyAppExeName}"" ""%1"""; Tasks: fileassochk

; 文件关联 - docx
Root: HKCR; Subkey: ".docx"; ValueType: string; ValueName: ""; ValueData: "FileTools.docx"; Flags: uninsdeletevalue; Tasks: fileassochk
Root: HKCR; Subkey: "FileTools.docx"; ValueType: string; ValueName: ""; ValueData: "Word文档"; Flags: uninsdeletekey; Tasks: fileassochk
Root: HKCR; Subkey: "FileTools.docx\shell\open\command"; ValueType: string; ValueName: ""; ValueData: """{app}\{#MyAppExeName}"" ""%1"""; Tasks: fileassochk

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
Type: filesandordirs; Name: "{app}\data"

[Code]
// 安装前检查
function InitializeSetup(): Boolean;
begin
  Result := True;

  // 检查是否已安装
  if RegKeyExists(HKEY_LOCAL_MACHINE, 'SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\{#MyAppId}') then
  begin
    if MsgBox('检测到已安装 FileTools。继续将升级现有版本。' + #13#10 + '是否继续？', mbConfirmation, MB_YESNO) = IDNO then
    begin
      Result := False;
      Exit;
    end;
  end;

  // 检查 Visual C++ Redistributable
  if not RegKeyExists(HKEY_LOCAL_MACHINE, 'SOFTWARE\Microsoft\VisualStudio\14.0\VC\Runtimes\x64') then
  begin
    MsgBox('建议安装 Visual C++ Redistributable 2015-2022 (x64) 以确保程序正常运行。' + #13#10 +
           '可从 Microsoft 官网下载: https://aka.ms/vs/17/release/vc_redist.x64.exe', mbInformation, MB_OK);
  end;
end;

// 安装后创建数据目录
procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssPostInstall then
  begin
    // 创建数据目录
    ForceDirectories(ExpandConstant('{app}\data\logs'));
    ForceDirectories(ExpandConstant('{app}\data\cache'));
    ForceDirectories(ExpandConstant('{app}\data\tantivy_index'));
    ForceDirectories(ExpandConstant('{app}\data\hnsw_index'));
  end;
end;
