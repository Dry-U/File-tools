; ============================================================
; File Tools - NSIS 安装脚本模板
; 由 scripts/build_installer.py 动态生成版本号和模式信息
; ============================================================

!include "MUI2.nsh"
!include "FileFunc.nsh"

; ===== 安装程序基本信息（由 Python 脚本覆盖）===
!define PRODUCT_NAME "FileTools"
!define PRODUCT_VERSION "___VERSION___"
!define PRODUCT_MODE "___MODE___"
!define PRODUCT_PUBLISHER "Darian"
!define PRODUCT_URL "https://github.com/darian/File-tools"
!define PRODUCT_DIR_REGKEY "Software\Microsoft\Windows\CurrentVersion\App Paths\FileTools.exe"
!define PRODUCT_UNINST_KEY "Software\Microsoft\Windows\CurrentVersion\Uninstall\${PRODUCT_NAME}"
!define PRODUCT_UNINST_ROOT_KEY "HKLM"

; ===== MUI 设置 =====
!define MUI_ABORTWARNING
!define MUI_ICON "frontend\static\logo.ico"
!define MUI_UNICON "frontend\static\logo.ico"
!define MUI_HEADERIMAGE
!define MUI_HEADERIMAGE_BITMAP ""

; ===== 安装页面 =====
!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_LICENSE "LICENSE"
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_PAGE_FINISH

; ===== 卸载页面 =====
!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES

; ===== 语言 =====
!insertmacro MUI_LANGUAGE "SimpChinese"
!insertmacro MUI_LANGUAGE "English"

; ===== 安装程序属性 =====
Name "${PRODUCT_NAME} v${PRODUCT_VERSION} (${PRODUCT_MODE})"
OutFile "dist\FileTools-${PRODUCT_MODE}-v${PRODUCT_VERSION}-Setup.exe"
InstallDir "$PROGRAMFILES64\${PRODUCT_NAME}"
InstallDirRegKey HKLM "${PRODUCT_DIR_REGKEY}" ""
ShowInstDetails show
ShowUnInstDetails show
RequestExecutionLevel admin

; ===== 版本信息 =====
VIProductVersion "${PRODUCT_VERSION}.0"
VIAddVersionKey "ProductName" "${PRODUCT_NAME}"
VIAddVersionKey "ProductVersion" "${PRODUCT_VERSION}"
VIAddVersionKey "FileDescription" "File Tools - ${PRODUCT_MODE} Edition"
VIAddVersionKey "FileVersion" "${PRODUCT_VERSION}"
VIAddVersionKey "CompanyName" "${PRODUCT_PUBLISHER}"

; ===== 安装段 =====
Section "MainSection" SEC01
    SetOutPath "$INSTDIR"
    SetOverwrite on

    ; 复制所有构建产物
    File /r "dist\FileTools-v${PRODUCT_VERSION}-${PRODUCT_MODE}\*.*"

    ; 创建数据目录
    CreateDirectory "$APPDATA\FileTools\data"
    CreateDirectory "$APPDATA\FileTools\data\logs"
    CreateDirectory "$APPDATA\FileTools\data\cache"

    ; 创建卸载器
    WriteUninstaller "$INSTDIR\uninst.exe"

    ; 写入注册表
    WriteRegStr HKLM "${PRODUCT_DIR_REGKEY}" "" "$INSTDIR\FileTools.exe"
    WriteRegStr ${PRODUCT_UNINST_ROOT_KEY} "${PRODUCT_UNINST_KEY}" "DisplayName" "$(^Name)"
    WriteRegStr ${PRODUCT_UNINST_ROOT_KEY} "${PRODUCT_UNINST_KEY}" "UninstallString" "$INSTDIR\uninst.exe"
    WriteRegStr ${PRODUCT_UNINST_ROOT_KEY} "${PRODUCT_UNINST_KEY}" "DisplayIcon" "$INSTDIR\FileTools.exe"
    WriteRegStr ${PRODUCT_UNINST_ROOT_KEY} "${PRODUCT_UNINST_KEY}" "DisplayVersion" "${PRODUCT_VERSION}"
    WriteRegStr ${PRODUCT_UNINST_ROOT_KEY} "${PRODUCT_UNINST_KEY}" "URLInfoAbout" "${PRODUCT_URL}"
    WriteRegStr ${PRODUCT_UNINST_ROOT_KEY} "${PRODUCT_UNINST_KEY}" "Publisher" "${PRODUCT_PUBLISHER}"
    WriteRegDWORD ${PRODUCT_UNINST_ROOT_KEY} "${PRODUCT_UNINST_KEY}" "NoModify" 1
    WriteRegDWORD ${PRODUCT_UNINST_ROOT_KEY} "${PRODUCT_UNINST_KEY}" "NoRepair" 1

    ; 创建开始菜单快捷方式
    CreateDirectory "$SMPROGRAMS\${PRODUCT_NAME}"
    CreateShortCut "$SMPROGRAMS\${PRODUCT_NAME}\FileTools.lnk" "$INSTDIR\FileTools.exe" "" "$INSTDIR\FileTools.exe" 0
    CreateShortCut "$SMPROGRAMS\${PRODUCT_NAME}\Uninstall.lnk" "$INSTDIR\uninst.exe"

    ; 创建桌面快捷方式
    CreateShortCut "$DESKTOP\FileTools.lnk" "$INSTDIR\FileTools.exe" "" "$INSTDIR\FileTools.exe" 0
SectionEnd

; ===== 卸载段 =====
Section Uninstall
    ; 停止运行中的进程
    nsExec::ExecToLog 'taskkill /F /IM FileTools.exe'

    ; 删除快捷方式
    Delete "$DESKTOP\FileTools.lnk"
    Delete "$SMPROGRAMS\${PRODUCT_NAME}\FileTools.lnk"
    Delete "$SMPROGRAMS\${PRODUCT_NAME}\Uninstall.lnk"
    RMDir "$SMPROGRAMS\${PRODUCT_NAME}"

    ; 删除注册表
    DeleteRegKey ${PRODUCT_UNINST_ROOT_KEY} "${PRODUCT_UNINST_KEY}"
    DeleteRegKey HKLM "${PRODUCT_DIR_REGKEY}"

    ; 删除安装目录
    RMDir /r "$INSTDIR"

    ; 提示是否删除用户数据
    MessageBox MB_YESNO|MB_ICONQUESTION "是否删除用户数据？$\n$\n（包括配置文件和索引数据）" IDYES DeleteUserData IDNO SkipUserData
    DeleteUserData:
        RMDir /r "$APPDATA\FileTools"
    SkipUserData:
SectionEnd
