// Prevents additional console window on Windows in release, DO NOT REMOVE!!
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use std::sync::Arc;
use tokio::sync::Mutex;
use tauri::{
    menu::{Menu, MenuItem},
    tray::TrayIconBuilder,
    Manager, RunEvent,
};

mod commands;
mod sidecar;
mod workspace;

use sidecar::PythonSidecar;
use workspace::Workspace;

pub struct AppState {
    pub sidecar: Arc<Mutex<Option<PythonSidecar>>>,
    pub workspace: Workspace,
}

fn main() {
    let app = tauri::Builder::default()
        .plugin(tauri_plugin_dialog::init())
        .invoke_handler(tauri::generate_handler![
            // 文件管理
            commands::file::upload_file,
            commands::file::list_files,
            commands::file::remove_file,
            commands::file::get_file_info,
            commands::file::export_file,
            commands::file::get_file_bytes,
            // Agent 通信
            commands::agent::chat,
            commands::agent::chat_stream,
            commands::agent::stop_chat,
            commands::agent::confirm_tool_call,
            // 会话管理
            commands::session::list_sessions,
            commands::session::create_session,
            commands::session::delete_session,
            commands::session::rollback,
            commands::session::get_snapshots,
            commands::session::get_history,
            // 配置
            commands::config::get_config,
            commands::config::save_config,
        ])
        .setup(|app| {
            // 初始化工作区目录
            let workspace = Workspace::init()?;

            // 启动 Python sidecar（可选，失败不阻塞启动）
            let sidecar = PythonSidecar::try_start()?;

            app.manage(AppState {
                sidecar: Arc::new(Mutex::new(sidecar)),
                workspace,
            });

            // 开发模式打开 DevTools
            #[cfg(debug_assertions)]
            {
                if let Some(window) = app.get_webview_window("main") {
                    let _ = window.open_devtools();
                }
            }

            // 系统托盘
            let quit_i = MenuItem::with_id(app, "quit", "退出", true, None::<&str>)?;
            let hide_i = MenuItem::with_id(app, "hide", "隐藏", true, None::<&str>)?;
            let show_i = MenuItem::with_id(app, "show", "显示", true, None::<&str>)?;
            let menu = Menu::with_items(app, &[&show_i, &hide_i, &quit_i])?;

            TrayIconBuilder::new()
                .menu(&menu)
                .on_menu_event(|app, event| match event.id.as_ref() {
                    "quit" => {
                        app.exit(0);
                    }
                    "hide" => {
                        if let Some(window) = app.get_webview_window("main") {
                            let _ = window.hide();
                        }
                    }
                    "show" => {
                        if let Some(window) = app.get_webview_window("main") {
                            let _ = window.show();
                            let _ = window.set_focus();
                        }
                    }
                    _ => {}
                })
                .build(app)?;

            Ok(())
        })
        .build(tauri::generate_context!())
        .expect("error while building tauri application");

    app.run(|_app_handle, event| {
        if let RunEvent::Exit = event {
            if let Some(state) = _app_handle.try_state::<AppState>() {
                let mut sidecar = state.sidecar.blocking_lock();
                if let Some(ref mut s) = &mut *sidecar {
                    let _ = s.shutdown();
                }
            }
        }
    });
}
