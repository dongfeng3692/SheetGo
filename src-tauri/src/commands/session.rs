use crate::AppState;
use serde::{Deserialize, Serialize};
use tauri::State;

#[derive(Serialize, Deserialize, Debug, Clone)]
#[serde(rename_all = "camelCase")]
pub struct Session {
    pub session_id: String,
    pub name: String,
    pub created_at: i64,
}

#[derive(Serialize, Deserialize, Debug, Clone)]
#[serde(rename_all = "camelCase")]
pub struct SnapshotInfo {
    pub snapshot_id: String,
    pub session_id: String,
    pub file_id: String,
    pub description: String,
    pub created_at: i64,
}

#[derive(Serialize, Deserialize, Debug, Clone)]
#[serde(rename_all = "camelCase")]
pub struct HistoryEntry {
    pub message_id: String,
    pub role: String,
    pub content: String,
    pub created_at: i64,
}

#[derive(Serialize, Deserialize, Debug, Clone)]
#[serde(rename_all = "camelCase")]
pub struct RollbackResult {
    pub success: bool,
    pub snapshot_id: String,
}

#[tauri::command]
pub async fn list_sessions(state: State<'_, AppState>) -> Result<Vec<Session>, String> {
    let workspace = &state.workspace;
    let mut sessions = vec![];
    let base = &workspace.base_dir;
    let workspace_dir = base.join("workspace");
    if let Ok(entries) = std::fs::read_dir(&workspace_dir) {
        for entry in entries.flatten() {
            let meta = entry.metadata();
            let created_at = meta
                .ok()
                .and_then(|m| m.created().ok())
                .and_then(|t| t.duration_since(std::time::UNIX_EPOCH).ok())
                .map(|d| d.as_secs() as i64)
                .unwrap_or(0);
            if let Some(name) = entry.file_name().to_str() {
                sessions.push(Session {
                    session_id: name.to_string(),
                    name: name.to_string(),
                    created_at,
                });
            }
        }
    }
    Ok(sessions)
}

#[tauri::command]
pub async fn create_session(name: String, state: State<'_, AppState>) -> Result<Session, String> {
    let session_id = uuid::Uuid::new_v4().to_string();
    state.workspace.create_session(&session_id)?;
    Ok(Session {
        session_id: session_id.clone(),
        name,
        created_at: chrono::Utc::now().timestamp(),
    })
}

#[tauri::command]
pub async fn delete_session(session_id: String, state: State<'_, AppState>) -> Result<(), String> {
    let session = state.workspace.get_session(&session_id)?;
    let path = session.base_dir().clone();
    if path.exists() {
        std::fs::remove_dir_all(path).map_err(|e| e.to_string())?;
    }
    Ok(())
}

#[tauri::command]
pub async fn get_snapshots(
    session_id: String,
    file_id: String,
    state: State<'_, AppState>,
) -> Result<Vec<SnapshotInfo>, String> {
    let session = state.workspace.get_session(&session_id)?;
    let snap_dir = &session.snapshot_dir;
    let mut snapshots = vec![];

    if let Ok(entries) = std::fs::read_dir(snap_dir) {
        for entry in entries.flatten() {
            let path = entry.path();
            if path.extension().map(|e| e == "json").unwrap_or(false) {
                if let Ok(content) = std::fs::read_to_string(&path) {
                    if let Ok(snap) = serde_json::from_str::<SnapshotInfo>(&content) {
                        if snap.file_id == file_id {
                            snapshots.push(snap);
                        }
                    }
                }
            }
        }
    }

    Ok(snapshots)
}

#[tauri::command]
pub async fn rollback(
    snapshot_id: String,
    _state: State<'_, AppState>,
) -> Result<RollbackResult, String> {
    // TODO: 调用 sidecar 或 session store 执行回滚
    Ok(RollbackResult {
        success: true,
        snapshot_id,
    })
}

#[tauri::command]
pub async fn get_history(session_id: String, _state: State<'_, AppState>) -> Result<Vec<HistoryEntry>, String> {
    // TODO: 从 SQLite 读取会话历史
    Ok(vec![HistoryEntry {
        message_id: "msg_1".to_string(),
        role: "user".to_string(),
        content: format!("Session {}", session_id),
        created_at: chrono::Utc::now().timestamp(),
    }])
}
