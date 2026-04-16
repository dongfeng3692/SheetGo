use crate::AppState;
use crate::sidecar::PythonSidecar;
use serde::{Deserialize, Serialize};
use serde_json::json;
use tauri::{Emitter, Manager, State};

#[derive(Serialize, Deserialize, Debug, Clone)]
#[serde(rename_all = "camelCase")]
pub struct ChatRequest {
    pub session_id: String,
    pub file_id: String,
    pub message: String,
}

#[derive(Serialize, Deserialize, Debug, Clone)]
#[serde(rename_all = "camelCase")]
pub struct ChatResponse {
    pub message_id: String,
    pub text: String,
    pub tool_calls: Option<Vec<serde_json::Value>>,
    pub modified_cells: Option<Vec<serde_json::Value>>,
}

#[tauri::command]
pub async fn chat(req: ChatRequest, state: State<'_, AppState>) -> Result<ChatResponse, String> {
    let params = json!({
        "session_id": req.session_id,
        "file_id": req.file_id,
        "message": req.message,
    });

    let result = {
        let mut guard = state.sidecar.lock().await;
        let sidecar = guard.as_mut().ok_or("Python 后端未启动".to_string())?;
        sidecar.call("chat", params).await?
    }; // guard dropped here

    Ok(ChatResponse {
        message_id: result["message_id"].as_str().unwrap_or("").to_string(),
        text: result["text"].as_str().unwrap_or("").to_string(),
        tool_calls: None,
        modified_cells: None,
    })
}

#[tauri::command]
pub async fn chat_stream(
    req: ChatRequest,
    app: tauri::AppHandle,
) -> Result<String, String> {
    let params = json!({
        "session_id": req.session_id,
        "file_id": req.file_id,
        "message": req.message,
    });
    let stream_id = uuid::Uuid::new_v4().to_string();

    // Spawn streaming work in background so invoke returns immediately
    let sidecar_arc = {
        let state = app.state::<AppState>();
        state.sidecar.clone()
    };
    let emit_app = app.clone();
    let error_app = app.clone();
    tokio::spawn(async move {
        let mut guard = sidecar_arc.lock().await;
        let sidecar: &mut PythonSidecar = match guard.as_mut() {
            Some(s) => s,
            None => {
                let _ = error_app.emit("chat-stream", json!({"type": "error", "error": "Python 后端未启动"}));
                return;
            }
        };
        let result = sidecar
            .call_stream("chat_stream", params, move |event: serde_json::Value| {
                let payload = if event.get("error").is_some() {
                    let msg = event["error"]["message"].as_str().unwrap_or("Unknown error");
                    json!({"type": "error", "error": msg})
                } else if event.get("result").is_some() {
                    json!({"type": "done"})
                } else {
                    event.get("params").cloned().unwrap_or(event)
                };
                let _ = emit_app.emit("chat-stream", payload);
            })
            .await;

        if let Err(e) = result {
            let _ = error_app.emit("chat-stream", json!({"type": "error", "error": e}));
        }
    });

    Ok(stream_id)
}

#[tauri::command]
pub async fn stop_chat(state: State<'_, AppState>) -> Result<(), String> {
    {
        let mut guard = state.sidecar.lock().await;
        let sidecar = guard.as_mut().ok_or("Python 后端未启动".to_string())?;
        sidecar.call("stop", json!({})).await?;
    }
    Ok(())
}

#[tauri::command]
pub async fn confirm_tool_call(
    call_id: String,
    state: State<'_, AppState>,
) -> Result<(), String> {
    {
        let mut guard = state.sidecar.lock().await;
        let sidecar = guard.as_mut().ok_or("Python 后端未启动".to_string())?;
        sidecar
            .call("confirm_tool_call", json!({ "callId": call_id }))
            .await?;
    }
    Ok(())
}
