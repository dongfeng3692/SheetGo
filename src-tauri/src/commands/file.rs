use crate::AppState;
use serde::{Deserialize, Serialize};
use serde_json::json;
use std::path::PathBuf;
use tauri::{Emitter, State};

#[derive(Serialize, Deserialize, Debug, Clone)]
#[serde(rename_all = "camelCase")]
pub struct UploadResult {
    pub file_id: String,
    pub file_name: String,
    pub sheets: Vec<String>,
    pub total_rows: u64,
}

#[derive(Serialize, Deserialize, Debug, Clone)]
#[serde(rename_all = "camelCase")]
pub struct FileInfo {
    pub file_id: String,
    pub file_name: String,
    pub sheets: Vec<String>,
    pub total_rows: u64,
}

/// 读取 schema.json 获取 sheets 和 totalRows
fn read_schema(cache_dir: &PathBuf, file_id: &str) -> (Vec<String>, u64) {
    let schema_path = cache_dir.join(format!("{}_schema.json", file_id));
    if let Ok(content) = std::fs::read_to_string(&schema_path) {
        if let Ok(value) = serde_json::from_str::<serde_json::Value>(&content) {
            let sheets: Vec<String> = value
                .get("sheets")
                .and_then(|s| s.as_array())
                .map(|arr| {
                    arr.iter()
                        .filter_map(|s| s.get("name").and_then(|n| n.as_str()).map(String::from))
                        .collect()
                })
                .unwrap_or_default();
            let total_rows: u64 = value
                .get("sheets")
                .and_then(|s| s.as_array())
                .map(|arr| {
                    arr.iter()
                        .filter_map(|s| s.get("rowCount").and_then(|r| r.as_u64()))
                        .sum()
                })
                .unwrap_or(0);
            return (sheets, total_rows);
        }
    }
    (vec![], 0)
}

async fn require_sidecar(state: &State<'_, AppState>) -> Result<(), String> {
    let has_sidecar = state.sidecar.lock().await.is_some();
    if !has_sidecar {
        return Err("Python 后端未启动，请检查 sidecar 配置".to_string());
    }
    Ok(())
}

#[tauri::command]
pub async fn upload_file(
    path: String,
    session_id: String,
    app: tauri::AppHandle,
    state: State<'_, AppState>,
) -> Result<UploadResult, String> {
    require_sidecar(&state).await?;
    let session = state.workspace.get_session(&session_id)?;
    let source_path = std::path::PathBuf::from(&path);
    let file_id = session.import_file(&source_path)?;
    let file_name = source_path
        .file_name()
        .and_then(|n| n.to_str())
        .unwrap_or("unknown")
        .to_string();

    let source_dest = session.source_dir.join(format!("{}.xlsx", file_id));
    let working_dest = session.working_dir.join(format!("{}.xlsx", file_id));
    let duckdb_path = session.cache_path(&file_id, "data.duckdb");
    let schema_path = session.cache_path(&file_id, "schema.json");
    let stats_path = session.cache_path(&file_id, "stats.json");

    {
        let mut guard = state.sidecar.lock().await;
        let sidecar = guard.as_mut().ok_or("Python 后端未启动".to_string())?;

        // 导入文件
        let import_params = json!({
            "sessionId": session_id,
            "fileId": file_id,
            "fileName": file_name,
            "sourcePath": source_dest.to_string_lossy(),
            "workingPath": working_dest.to_string_lossy(),
        });
        sidecar.call("file.import", import_params).await?;

        // 预加载（流式，转发进度事件到前端）
        let preload_params = json!({
            "fileId": file_id,
            "sourcePath": source_dest.to_string_lossy(),
            "workingPath": working_dest.to_string_lossy(),
            "duckdbPath": duckdb_path.to_string_lossy(),
            "schemaPath": schema_path.to_string_lossy(),
            "statsPath": stats_path.to_string_lossy(),
        });
        sidecar
            .call_stream("preload.start", preload_params, move |event| {
                let payload = if event.get("error").is_some() {
                    let msg = event["error"]["message"].as_str().unwrap_or("Unknown error");
                    json!({"stage": "done", "progress": 100, "message": msg})
                } else if event.get("result").is_some() {
                    json!({"stage": "done", "progress": 100})
                } else {
                    event.get("params").cloned().unwrap_or(event)
                };
                let _ = app.emit("preload-progress", payload);
            })
            .await?;
    } // guard dropped

    // 从 schema.json 读取 sheets 信息
    let (sheets, total_rows) = read_schema(&session.cache_dir, &file_id);

    Ok(UploadResult {
        file_id,
        file_name,
        sheets,
        total_rows,
    })
}

#[tauri::command]
pub async fn list_files(
    session_id: String,
    state: State<'_, AppState>,
) -> Result<Vec<FileInfo>, String> {
    let session = state.workspace.get_session(&session_id)?;
    let mut files = vec![];

    let guard = state.sidecar.lock().await;
    if let Some(_sidecar) = guard.as_ref() {
        // sidecar 可用但需要 &mut，无法在这里调用 RPC
        // 降级为文件系统扫描
        let _ = _sidecar;
    }

    // 扫描 working 目录中的 Excel 文件
    if let Ok(entries) = std::fs::read_dir(&session.working_dir) {
        for entry in entries.flatten() {
            let path = entry.path();
            if path
                .extension()
                .map(|e| e == "xlsx" || e == "xls")
                .unwrap_or(false)
            {
                let stem = path
                    .file_stem()
                    .and_then(|s| s.to_str())
                    .unwrap_or("")
                    .to_string();
                let (sheets, total_rows) = read_schema(&session.cache_dir, &stem);
                files.push(FileInfo {
                    file_id: stem,
                    file_name: path
                        .file_name()
                        .and_then(|n| n.to_str())
                        .unwrap_or("")
                        .to_string(),
                    sheets,
                    total_rows,
                });
            }
        }
    }

    Ok(files)
}

#[tauri::command]
pub async fn remove_file(
    file_id: String,
    session_id: String,
    state: State<'_, AppState>,
) -> Result<(), String> {
    let session = state.workspace.get_session(&session_id)?;

    for dir in [&session.source_dir, &session.working_dir, &session.cache_dir] {
        if let Ok(entries) = std::fs::read_dir(dir) {
            for entry in entries.flatten() {
                let name = entry.file_name();
                let name_str = name.to_string_lossy();
                if name_str.starts_with(&file_id) {
                    let _ = std::fs::remove_file(entry.path());
                }
            }
        }
    }

    Ok(())
}

#[tauri::command]
pub async fn get_file_info(
    file_id: String,
    session_id: String,
    state: State<'_, AppState>,
) -> Result<FileInfo, String> {
    let session = state.workspace.get_session(&session_id)?;
    let working = session.working_dir.join(format!("{}.xlsx", file_id));
    if !working.exists() {
        return Err("File not found".to_string());
    }
    let (sheets, total_rows) = read_schema(&session.cache_dir, &file_id);
    Ok(FileInfo {
        file_id,
        file_name: working
            .file_name()
            .and_then(|n| n.to_str())
            .unwrap_or("")
            .to_string(),
        sheets,
        total_rows,
    })
}

#[tauri::command]
pub async fn export_file(
    file_id: String,
    session_id: String,
    dest_path: String,
    state: State<'_, AppState>,
) -> Result<(), String> {
    let session = state.workspace.get_session(&session_id)?;
    let working = session.working_dir.join(format!("{}.xlsx", file_id));
    if !working.exists() {
        return Err("File not found".to_string());
    }
    std::fs::copy(&working, &dest_path).map_err(|e| e.to_string())?;
    Ok(())
}

use base64::Engine;

#[tauri::command]
pub async fn get_file_bytes(
    file_id: String,
    session_id: String,
    state: State<'_, AppState>,
) -> Result<String, String> {
    let session = state.workspace.get_session(&session_id)?;
    let working = session.working_dir.join(format!("{}.xlsx", file_id));
    if !working.exists() {
        return Err("File not found".to_string());
    }
    let bytes = std::fs::read(working).map_err(|e| e.to_string())?;
    Ok(base64::engine::general_purpose::STANDARD_NO_PAD.encode(&bytes))
}
