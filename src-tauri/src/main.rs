// Prevents additional console window on Windows in release
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use log::{error, info, warn};
use parking_lot::Mutex;
use std::sync::atomic::{AtomicU64, Ordering};
use std::time::Duration;
use tauri::{AppHandle, Emitter, Manager, RunEvent};

/// 存储后端进程 PID，用于应用关闭时终止
struct BackendProcess(Mutex<Option<u32>>);

impl BackendProcess {
    fn new(pid: u32) -> Self {
        Self(Mutex::new(Some(pid)))
    }
}

impl Drop for BackendProcess {
    fn drop(&mut self) {
        let mut pid_guard = self.0.lock();
        if let Some(pid) = pid_guard.take() {
            info!("BackendProcess 被释放，正在终止进程 PID: {}", pid);
            // 使用 taskkill /F /T 强制终止进程树（更可靠）
            #[cfg(windows)]
            {
                let _ = std::process::Command::new("taskkill")
                    .args(["/F", "/T", "/PID", &pid.to_string()])
                    .output();
                info!("已发送 taskkill /F /T 命令给进程 {}", pid);
            }
            #[cfg(unix)]
            {
                let _ = std::process::Command::new("kill")
                    .args(["-9", &pid.to_string()])
                    .output();
            }
            info!("BackendProcess 进程已终止");
        }
    }
}

/// 后端生命周期状态
#[derive(Debug, Clone, Copy, PartialEq)]
enum BackendStatus {
    Starting, // 正在启动
    Running,  // 运行中
    Failed,   // 启动失败
    Stopping, // 正在停止
    Stopped,  // 已停止
}

impl BackendStatus {
    fn as_str(&self) -> &'static str {
        match self {
            BackendStatus::Starting => "starting",
            BackendStatus::Running => "running",
            BackendStatus::Failed => "failed",
            BackendStatus::Stopping => "stopping",
            BackendStatus::Stopped => "stopped",
        }
    }
}

/// 后端状态管理（使用 tauri::State<T> 管理）
struct BackendState {
    status: Mutex<BackendStatus>,
    status_time: AtomicU64,
}

impl BackendState {
    fn new() -> Self {
        Self {
            status: Mutex::new(BackendStatus::Starting),
            status_time: AtomicU64::new(0),
        }
    }

    /// 更新后端状态
    fn set_status(&self, status: BackendStatus) {
        let mut guard = self.status.lock();
        *guard = status;
        self.status_time.store(
            std::time::SystemTime::now()
                .duration_since(std::time::UNIX_EPOCH)
                .unwrap_or_default()
                .as_secs(),
            Ordering::SeqCst,
        );
    }

    /// 获取当前状态（检查超时）
    fn get_status(&self) -> BackendStatus {
        let status = *self.status.lock();

        // 检查 Starting 状态是否超时（30秒）
        if status == BackendStatus::Starting {
            let start_time = self.status_time.load(Ordering::SeqCst);
            let now = std::time::SystemTime::now()
                .duration_since(std::time::UNIX_EPOCH)
                .unwrap_or_default()
                .as_secs();

            if start_time > 0 && now - start_time > 30 {
                warn!("后端启动超时（30秒），标记为失败");
                self.set_status(BackendStatus::Failed);
                return BackendStatus::Failed;
            }
        }

        status
    }

    /// 检查状态是否超时
    fn is_starting_timeout(&self) -> bool {
        let status = *self.status.lock();
        if status != BackendStatus::Starting {
            return false;
        }

        let start_time = self.status_time.load(Ordering::SeqCst);
        let now = std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .unwrap_or_default()
            .as_secs();

        start_time > 0 && now - start_time > 30
    }
}

// 全局后端状态（用于在 tauri::State 可用前的初始化阶段）
use std::sync::OnceLock;
static BACKEND_STATE_GLOBAL: OnceLock<BackendState> = OnceLock::new();

/// 获取全局后端状态实例
fn get_backend_state() -> &'static BackendState {
    BACKEND_STATE_GLOBAL.get_or_init(|| BackendState::new())
}

/// 更新后端状态（使用全局状态）
fn set_backend_status(status: BackendStatus) {
    get_backend_state().set_status(status);
}

/// 获取后端状态（使用全局状态）
fn get_backend_status_internal() -> BackendStatus {
    get_backend_state().get_status()
}

/// 检查状态是否超时（使用全局状态）
fn is_starting_timeout() -> bool {
    get_backend_state().is_starting_timeout()
}

/// 启动 Python FastAPI 后端进程
fn start_python_backend(app: &tauri::App) -> Result<BackendProcess, Box<dyn std::error::Error>> {
    info!("启动 Python FastAPI 后端...");

    // 状态流转: -> Starting
    set_backend_status(BackendStatus::Starting);
    let _ = app.emit("backend-status-changed", "starting");

    #[cfg(debug_assertions)]
    {
        // 开发模式：直接运行 python main.py，修改代码后无需重新编译
        let project_root = std::path::Path::new(env!("CARGO_MANIFEST_DIR"))
            .parent()
            .ok_or("Invalid project structure: CARGO_MANIFEST_DIR has no parent")?
            .to_path_buf();

        // 尝试多个 Python 解释器
        let python_candidates = if cfg!(windows) {
            vec!["python.exe", "python", "py"]
        } else {
            vec!["python3", "python"]
        };

        let main_py = project_root.join("main.py");
        if !main_py.exists() {
            return Err(format!("main.py not found at: {}", main_py.display()).into());
        }

        let mut last_error = None;
        for python_exe in &python_candidates {
            info!("开发模式：尝试运行 {} {}", python_exe, main_py.display());

            let mut cmd = std::process::Command::new(python_exe);
            cmd.arg(&main_py).current_dir(&project_root);
            // 设置环境变量，优先使用固定端口
            cmd.env("FILETOOLS_PORT", "18642");

            match cmd.spawn() {
                Ok(child) => {
                    let pid = child.id();
                    info!("Python FastAPI 后端已启动 (PID: {:?})", pid);
                    return Ok(BackendProcess::new(pid));
                }
                Err(e) => {
                    warn!("尝试 {} 失败: {}", python_exe, e);
                    last_error = Some(e);
                }
            }
        }

        Err(format!(
            "启动后端失败: 无法找到可用的 Python 解释器。最后错误: {:?}",
            last_error
        )
        .into())
    }

    #[cfg(not(debug_assertions))]
    {
        // 发布模式：运行 PyInstaller 打包的 sidecar
        use tauri_plugin_shell::ShellExt;
        let sidecar = app.shell().sidecar("filetools_backend")?;
        info!("Sidecar 路径: {:?}", sidecar);

        // Tauri v2: 直接 spawn sidecar
        let (_rx, child) = sidecar
            .spawn()
            .map_err(|e| format!("启动后端失败: {}", e))?;

        let pid = child.pid();
        info!("Python FastAPI 后端已启动 (PID: {:?})", pid);

        Ok(BackendProcess::new(pid))
    }
}

/// 从 Python 写入的端口文件读取实际端口
fn read_backend_port() -> Option<u16> {
    use std::io::Read;

    // 与 Python 保持一致的端口文件路径
    let temp_dir = std::env::temp_dir();
    let port_file = temp_dir.join("filetools_backend_port.txt");

    if !port_file.exists() {
        warn!("端口文件不存在: {:?}", port_file);
        return None;
    }

    match std::fs::File::open(&port_file) {
        Ok(mut file) => {
            let mut contents = String::new();
            if file.read_to_string(&mut contents).is_ok() {
                let port = contents.trim().parse::<u16>().ok();
                if port.is_some() {
                    info!("从 {:?} 读取到后端端口: {}", port_file, port.unwrap());
                }
                return port;
            }
        }
        Err(e) => {
            warn!("读取端口文件失败: {:?}", e);
        }
    }
    None
}

/// 获取后端实际端口（供前端动态发现）
#[tauri::command]
fn get_backend_port() -> u16 {
    read_backend_port().unwrap_or(18642)
}

/// 显示后端启动错误对话框
fn show_backend_error_dialog(app: &AppHandle, error: &str) {
    warn!("准备显示后端启动错误对话框: {}", error);
    error!("后端启动失败: {}", error);
    let _ = app.emit("backend-start-error", error.to_string());
}

/// 最小化窗口
#[tauri::command]
fn minimize_window(app: AppHandle) {
    if let Some(window) = app.get_webview_window("main") {
        let _ = window.minimize();
    }
}

/// 切换最大化/还原
#[tauri::command]
fn toggle_maximize(app: AppHandle) {
    if let Some(window) = app.get_webview_window("main") {
        if window.is_maximized().unwrap_or(false) {
            let _ = window.unmaximize();
        } else {
            let _ = window.maximize();
        }
    }
}

/// 关闭窗口
#[tauri::command]
fn close_window(app: AppHandle) {
    if let Some(window) = app.get_webview_window("main") {
        let _ = window.close();
    }
}

/// 还原窗口
#[tauri::command]
fn restore_window(app: AppHandle) {
    if let Some(window) = app.get_webview_window("main") {
        let _ = window.unmaximize();
    }
}

/// 获取窗口是否最大化
#[tauri::command]
fn is_maximized(app: AppHandle) -> bool {
    app.get_webview_window("main")
        .map(|w| w.is_maximized().unwrap_or(false))
        .unwrap_or(false)
}

/// 后端健康状态响应
#[derive(serde::Serialize)]
struct HealthStatus {
    status: String,
    pid: Option<u32>,
}

/// 获取后端状态命令
#[tauri::command]
fn get_backend_status() -> String {
    // 检查是否超时
    if is_starting_timeout() {
        return "timeout".to_string();
    }
    get_backend_status_internal().as_str().to_string()
}

/// 检查后端健康状态（实时查询进程状态）
#[tauri::command]
fn check_backend_health(process: tauri::State<BackendProcess>) -> HealthStatus {
    let pid = process.0.lock().unwrap_or(0);
    if pid == 0 {
        return HealthStatus {
            status: "stopped".to_string(),
            pid: None,
        };
    }

    // 检查进程是否存在
    #[cfg(windows)]
    {
        let output = std::process::Command::new("tasklist")
            .arg("/FI")
            .arg(&format!("PID eq {}", pid))
            .output();

        if let Ok(out) = output {
            let stdout = String::from_utf8_lossy(&out.stdout);
            if stdout.contains(&pid.to_string()) {
                return HealthStatus {
                    status: "running".to_string(),
                    pid: Some(pid),
                };
            }
        }
    }

    HealthStatus {
        status: "stopped".to_string(),
        pid: None,
    }
}

/// 优雅地停止 Python 后端进程
fn stop_python_backend(app_handle: &AppHandle, process: &BackendProcess) {
    // 状态流转: Running -> Stopping
    set_backend_status(BackendStatus::Stopping);
    let _ = app_handle.emit("backend-status-changed", "stopping");

    let mut pid_guard = process.0.lock();
    let pid = pid_guard.take().unwrap_or(0);

    if pid == 0 {
        info!("后端进程 PID 为 0，假设已退出");
        set_backend_status(BackendStatus::Stopped);
        let _ = app_handle.emit("backend-status-changed", "stopped");
        return;
    }

    info!("正在终止后端进程 (PID: {})...", pid);

    #[cfg(windows)]
    {
        // 首先尝试通过 HTTP 请求通知 Python 后端主动退出（最优雅）
        let port = read_backend_port().unwrap_or(18642);
        let shutdown_url = format!("http://127.0.0.1:{}/api/shutdown", port);
        info!("尝试连接到后端端口 {} 进行优雅关闭...", port);

        match reqwest::blocking::Client::new()
            .post(&shutdown_url)
            .timeout(Duration::from_secs(2))
            .send()
        {
            Ok(_) => {
                info!("已发送 HTTP 优雅关闭请求到端口 {}", port);
            }
            Err(e) => {
                info!("HTTP 关闭请求失败 (端口 {}): {}，将使用 taskkill", port, e);
            }
        }
    }

    // 等待一小段时间让进程优雅退出
    std::thread::sleep(Duration::from_secs(2));

    // 使用 taskkill 强制终止进程树
    #[cfg(windows)]
    {
        let _ = std::process::Command::new("taskkill")
            .args(["/F", "/T", "/PID", &pid.to_string()])
            .output();
    }
    #[cfg(unix)]
    {
        let _ = std::process::Command::new("kill")
            .args(["-9", &pid.to_string()])
            .output();
    }

    info!("后端进程已终止");
    set_backend_status(BackendStatus::Stopped);
    let _ = app_handle.emit("backend-status-changed", "stopped");
}

/// 强制终止后端进程命令
#[tauri::command]
fn kill_backend(process: tauri::State<BackendProcess>) -> Result<String, String> {
    let mut pid_guard = process.0.lock();
    let pid = pid_guard.take().unwrap_or(0);

    if pid == 0 {
        return Ok("进程已退出".to_string());
    }

    #[cfg(windows)]
    {
        let output = std::process::Command::new("taskkill")
            .args(["/F", "/T", "/PID", &pid.to_string()])
            .output();

        match output {
            Ok(_) => {
                set_backend_status(BackendStatus::Stopped);
                Ok(format!("进程 {} 已强制终止", pid))
            }
            Err(e) => Err(format!("终止进程失败: {}", e)),
        }
    }
    #[cfg(not(windows))]
    {
        let output = std::process::Command::new("kill")
            .args(["-9", &pid.to_string()])
            .output();

        match output {
            Ok(_) => {
                set_backend_status(BackendStatus::Stopped);
                Ok(format!("进程 {} 已强制终止", pid))
            }
            Err(e) => Err(format!("终止进程失败: {}", e)),
        }
    }
}

/// 重启后端进程命令
/// 注意：此命令会终止现有进程，但新进程需要应用重启后由 setup 启动
#[tauri::command]
fn restart_backend(
    app_handle: AppHandle,
    process: tauri::State<BackendProcess>,
) -> Result<String, String> {
    // 1. 停止现有进程
    stop_python_backend(&app_handle, &process);

    // 2. 更新状态
    set_backend_status(BackendStatus::Stopped);
    let _ = app_handle.emit("backend-status-changed", "stopped");

    // 3. 提示用户需要重启应用
    Ok("后端进程已停止，请重启应用以启动新进程".to_string())
}

/// 打开外部 URL（在默认浏览器中）
#[tauri::command]
fn open_external_url(url: String) -> Result<(), String> {
    // 使用 std::process::Command 打开默认浏览器
    #[cfg(target_os = "windows")]
    {
        std::process::Command::new("cmd")
            .args(["/C", "start", "", &url])
            .spawn()
            .map_err(|e| format!("打开URL失败: {}", e))?;
    }
    #[cfg(target_os = "macos")]
    {
        std::process::Command::new("open")
            .arg(&url)
            .spawn()
            .map_err(|e| format!("打开URL失败: {}", e))?;
    }
    #[cfg(target_os = "linux")]
    {
        std::process::Command::new("xdg-open")
            .arg(&url)
            .spawn()
            .map_err(|e| format!("打开URL失败: {}", e))?;
    }
    Ok(())
}

/// 选择目录（通过 Rust API 绕过 URL 限制）
/// 使用 spawn_blocking 在后台线程执行 blocking_pick_folder
#[tauri::command]
async fn pick_directory(app_handle: tauri::AppHandle) -> Result<Option<String>, String> {
    use tauri_plugin_dialog::DialogExt;
    use std::sync::mpsc;

    // 使用 channel 从后台线程获取结果
    let (tx, rx) = mpsc::channel();

    // 在后台线程运行 blocking_pick_folder（spawn_blocking 不会阻塞 Tauri 主线程）
    let _ = tauri::async_runtime::spawn_blocking(move || {
        let result = app_handle.dialog().file().blocking_pick_folder();
        let path = match result {
            Some(p) => {
                let path_str = p.to_string();
                if path_str.starts_with("file://") {
                    Some(path_str[7..].to_string())
                } else {
                    Some(path_str)
                }
            }
            None => None,
        };
        let _ = tx.send(path);
    }).await;

    // 等待后台线程发送结果
    match rx.recv() {
        Ok(path) => Ok(path),
        Err(_) => Err("获取目录选择结果失败".to_string()),
    }
}

fn main() -> Result<(), Box<dyn std::error::Error>> {
    // 初始化日志
    env_logger::Builder::from_env(env_logger::Env::default().default_filter_or("info"))
        .format_timestamp_millis()
        .init();

    info!("FileTools 启动中...");

    let app = tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .plugin(tauri_plugin_dialog::init())
        .invoke_handler(tauri::generate_handler![
            minimize_window,
            toggle_maximize,
            close_window,
            restore_window,
            is_maximized,
            check_backend_health,
            get_backend_status,
            kill_backend,
            restart_backend,
            get_backend_port,
            open_external_url,
            pick_directory,
        ])
        .setup(|app| {
            match start_python_backend(app) {
                Ok(process) => {
                    let pid = process.0.lock().unwrap_or(0);
                    info!("后端进程已启动，PID: {:?}", pid);

                    // 先隐藏主窗口，等后端真正就绪后再显示
                    if let Some(main_window) = app.get_webview_window("main") {
                        let _ = main_window.hide();
                    }

                    // 启动后台任务：等待后端真正就绪后显示窗口
                    let app_handle = app.handle().clone();
                    tauri::async_runtime::spawn(async move {
                        // 等待后端就绪（最多60秒）
                        let max_wait = 60;
                        let port = read_backend_port().unwrap_or(18642);

                        info!("等待后端就绪于端口 {}...", port);

                        for i in 0..max_wait {
                            // 使用 TcpStream 检查端口是否可用
                            if std::net::TcpStream::connect_timeout(
                                &std::net::SocketAddr::from(([127, 0, 0, 1], port)),
                                std::time::Duration::from_secs(1),
                            ).is_ok() {
                                info!("后端已就绪，耗时 {} 轮", i);

                                // 短暂等待确保 FastAPI 完全初始化
                                std::thread::sleep(std::time::Duration::from_millis(300));

                                // 状态流转: Starting -> Running
                                set_backend_status(BackendStatus::Running);
                                let _ = app_handle.emit("backend-status-changed", "running");
                                let _ = app_handle.emit("backend-started", ());

                                // 显示主窗口
                                if let Some(main_window) = app_handle.get_webview_window("main") {
                                    let _ = main_window.show();
                                    let _ = main_window.set_focus();
                                }
                                return;
                            }
                            std::thread::sleep(std::time::Duration::from_millis(500));
                        }

                        // 超时
                        error!("后端启动超时（{}秒）", max_wait);
                        set_backend_status(BackendStatus::Failed);
                        let _ = app_handle.emit("backend-status-changed", "failed");
                        show_backend_error_dialog(&app_handle, "后端启动超时，请检查配置");
                    });

                    app.manage(process);
                }
                Err(e) => {
                    let error_msg = format!("{}", e);
                    error!("启动后端失败: {}", error_msg);

                    // 状态流转: Starting -> Failed
                    set_backend_status(BackendStatus::Failed);
                    let _ = app.emit("backend-status-changed", "failed");
                    show_backend_error_dialog(app.handle(), &error_msg);
                }
            }
            Ok(())
        })
        .build(tauri::generate_context!())
        .map_err(|e| {
            error!("构建 Tauri 应用失败: {}", e);
            e
        })?;

    app.run(|app_handle, event| match event {
        RunEvent::ExitRequested { api: _, .. } => {
            info!("收到退出请求，准备关闭后端进程...");
            if let Some(process) = app_handle.try_state::<BackendProcess>() {
                stop_python_backend(app_handle, &process);
            }
            info!("应用即将退出");
            // 停止后端后再允许退出（不再阻止退出）
            // api.prevent_exit() 会阻止退出，只有需要异步清理时才用
        }
        RunEvent::Exit => {
            info!("应用已退出");
        }
        _ => {}
    });

    Ok(())
}
