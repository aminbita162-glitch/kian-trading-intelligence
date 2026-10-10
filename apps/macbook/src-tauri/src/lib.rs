/// Kian Trading Intelligence — Tauri MacBook application library.
///
/// Per AD-030 (Unified MacBook and iPhone Experience): provide consistent
/// trading, mining, financial, scheduling, security, and incident-management
/// interfaces backed by cloud authorization.
///
/// Per AD-031 (Technology Direction): Tauri for the MacBook application.
///
/// The Tauri shell wraps the same React/TypeScript web frontend served by
/// Vite, providing native macOS window management, CSP enforcement, and
/// platform integration. The client is NOT a trusted financial execution
/// authority (Section 03.1) — all execution is cloud-authorized.
use tauri::Manager;

/// Show the main application window on startup.
fn show_main_window(app: &tauri::App) {
    if let Some(window) = app.get_webview_window("main") {
        let _ = window.show();
    }
}

/// Run the Tauri application.
pub fn run() {
    tauri::Builder::default()
        .setup(|app| {
            show_main_window(app);
            Ok(())
        })
        .run(tauri::generate_context!())
        .expect("error while running Kian Trading Intelligence Tauri application");
}
