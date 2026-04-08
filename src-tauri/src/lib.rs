// lib.rs - Re-exported for potential mobile entry point
// All commands are defined in main.rs for the desktop binary

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    // Desktop entry point is main.rs
    // This function is only used for mobile targets
}
