use serde_json::{json, Value};
use std::io::{BufRead, BufReader, Write};
use std::path::PathBuf;
use std::process::{Child, ChildStdin, ChildStdout};
use std::sync::atomic::{AtomicU64, Ordering};
use std::sync::{Arc, Mutex};

static REQUEST_ID: AtomicU64 = AtomicU64::new(1);

pub struct PythonSidecar {
    process: Child,
    stdin: Arc<Mutex<ChildStdin>>,
    stdout: Arc<Mutex<BufReader<ChildStdout>>>,
}

// SAFETY: PythonSidecar 的字段都是线程安全的（进程句柄、Mutex 保护的 IO）。
// Windows 上的 Child/ChildStdin/ChildStdout 逻辑上可跨线程使用。
unsafe impl Send for PythonSidecar {}

impl PythonSidecar {
    /// 启动 Python sidecar 进程
    pub fn try_start() -> Result<Option<Self>, String> {
        let python_path = Self::find_python()?;
        let project_root = Self::find_project_root()?;

        let mut process = std::process::Command::new(python_path)
            .env("PYTHONUTF8", "1")
            .args(["-c", "from python.main import main; main()"])
            .current_dir(project_root)
            .stdin(std::process::Stdio::piped())
            .stdout(std::process::Stdio::piped())
            .stderr(std::process::Stdio::inherit())
            .spawn()
            .map_err(|e| format!("Failed to start Python sidecar: {}", e))?;

        let stdin = process.stdin.take().ok_or("Failed to capture stdin")?;
        let stdout = process.stdout.take().ok_or("Failed to capture stdout")?;

        eprintln!("Python sidecar started successfully");

        Ok(Some(PythonSidecar {
            process,
            stdin: Arc::new(Mutex::new(stdin)),
            stdout: Arc::new(Mutex::new(BufReader::new(stdout))),
        }))
    }

    fn find_python() -> Result<String, String> {
        for name in &["python", "python3"] {
            if which_exists(name) {
                return Ok(name.to_string());
            }
        }
        Err("Python not found in PATH".to_string())
    }

    fn find_project_root() -> Result<PathBuf, String> {
        // 可执行文件在 src-tauri/ 下，项目根目录是其父目录
        let exe_dir = std::env::current_exe()
            .map_err(|e| e.to_string())?
            .parent()
            .ok_or("No parent dir")?
            .to_path_buf();

        // 开发模式：exe 在 target/debug/
        if exe_dir.ends_with("debug") || exe_dir.ends_with("release") {
            let mut p = exe_dir.clone();
            for _ in 0..3 {
                p = p.parent().ok_or("No parent")?.to_path_buf();
            }
            return Ok(p);
        }

        // 生产模式：exe 在项目根目录或旁边
        let mut p = exe_dir;
        for _ in 0..3 {
            if p.join("python").join("main.py").exists() {
                return Ok(p);
            }
            p = p.parent().ok_or("No parent")?.to_path_buf();
        }

        Err("Cannot find project root (python/main.py)".to_string())
    }

    /// 发送 JSON-RPC 请求并等待响应（跳过中间的通知消息）
    pub async fn call(&mut self, method: &str, params: Value) -> Result<Value, String> {
        let id = REQUEST_ID.fetch_add(1, Ordering::SeqCst);
        let request = json!({
            "jsonrpc": "2.0",
            "id": id,
            "method": method,
            "params": params,
        });

        let request_line = request.to_string() + "\n";
        {
            let mut stdin = self.stdin.lock().map_err(|e| e.to_string())?;
            stdin
                .write_all(request_line.as_bytes())
                .map_err(|e| e.to_string())?;
            stdin.flush().map_err(|e| e.to_string())?;
        }

        // 读取响应，跳过通知消息（没有 id 的 JSON-RPC 消息）
        let stdout = Arc::clone(&self.stdout);
        let response = tokio::task::spawn_blocking(move || {
            let mut reader = stdout.lock().map_err(|e| e.to_string())?;
            loop {
                let mut line = String::new();
                reader.read_line(&mut line).map_err(|e| e.to_string())?;
                if line.trim().is_empty() {
                    continue;
                }
                let value: Value = serde_json::from_str(&line)
                    .map_err(|e| format!("Parse error: {} in '{}'", e, line.trim()))?;
                if value.get("id").is_some() {
                    return Ok::<Value, String>(value);
                }
                // 通知消息，继续读
            }
        })
        .await
        .map_err(|e| e.to_string())??;

        if let Some(error) = response.get("error") {
            return Err(error.to_string());
        }
        Ok(response.get("result").cloned().unwrap_or(Value::Null))
    }

    /// 发送流式请求，通过回调推送事件
    pub async fn call_stream<F>(
        &mut self,
        method: &str,
        params: Value,
        mut on_event: F,
    ) -> Result<(), String>
    where
        F: FnMut(Value) + Send + 'static,
    {
        let id = REQUEST_ID.fetch_add(1, Ordering::SeqCst);
        let request = json!({
            "jsonrpc": "2.0",
            "id": id,
            "method": method,
            "params": params,
        });

        let request_line = request.to_string() + "\n";
        {
            let mut stdin = self.stdin.lock().map_err(|e| e.to_string())?;
            stdin
                .write_all(request_line.as_bytes())
                .map_err(|e| e.to_string())?;
            stdin.flush().map_err(|e| e.to_string())?;
        }

        let stdout = Arc::clone(&self.stdout);
        tokio::task::spawn_blocking(move || {
            let mut reader = stdout.lock().map_err(|e| e.to_string())?;
            loop {
                let mut line = String::new();
                match reader.read_line(&mut line) {
                    Ok(0) => break,
                    Ok(_) => {
                        if let Ok(value) = serde_json::from_str::<Value>(&line) {
                                let has_id = value.get("id").is_some();
                                let is_done = value.get("result").is_some()
                                    || value.get("error").is_some();
                                if has_id && is_done {
                                    on_event(value);
                                    break;
                                }
                                on_event(value);
                            }
                    }
                    Err(e) => return Err(e.to_string()),
                }
            }
            Ok::<(), String>(())
        })
        .await
        .map_err(|e| e.to_string())??;

        Ok(())
    }

    pub fn shutdown(&mut self) -> Result<(), String> {
        self.process.kill().map_err(|e| e.to_string())
    }
}

impl Drop for PythonSidecar {
    fn drop(&mut self) {
        let _ = self.shutdown();
    }
}

fn which_exists(name: &str) -> bool {
    std::process::Command::new(name)
        .arg("--version")
        .stdout(std::process::Stdio::null())
        .stderr(std::process::Stdio::null())
        .status()
        .is_ok()
}
