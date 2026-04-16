use std::fs;
use std::path::PathBuf;

pub struct Workspace {
    pub base_dir: PathBuf,
}

pub struct SessionWorkspace {
    pub base_dir: PathBuf,
    pub source_dir: PathBuf,
    pub working_dir: PathBuf,
    pub cache_dir: PathBuf,
    pub snapshot_dir: PathBuf,
    pub export_dir: PathBuf,
}

impl SessionWorkspace {
    pub fn base_dir(&self) -> &PathBuf {
        &self.base_dir
    }

    /// 复制上传文件到 source/ 和 working/
    pub fn import_file(&self, source_path: &PathBuf) -> Result<String, String> {
        let file_name = source_path
            .file_stem()
            .and_then(|s| s.to_str())
            .ok_or("Invalid file name")?;
        let ext = source_path
            .extension()
            .and_then(|s| s.to_str())
            .unwrap_or("xlsx");
        let file_id = format!("{}_{}", file_name, uuid::Uuid::new_v4().to_string().split('-').next().unwrap_or(""));
        let dest_name = format!("{}.{}", file_id, ext);
        let source_dest = self.source_dir.join(&dest_name);
        let working_dest = self.working_dir.join(&dest_name);
        fs::copy(source_path, source_dest).map_err(|e| e.to_string())?;
        fs::copy(source_path, working_dest).map_err(|e| e.to_string())?;
        Ok(file_id)
    }

    /// 获取缓存路径
    pub fn cache_path(&self, file_id: &str, suffix: &str) -> PathBuf {
        self.cache_dir.join(format!("{}_{}", file_id, suffix))
    }

    /// 获取最新快照
    pub fn latest_snapshot(&self) -> Option<PathBuf> {
        let mut entries: Vec<_> = fs::read_dir(&self.snapshot_dir)
            .ok()?
            .flatten()
            .filter(|e| e.path().extension().map(|ext| ext == "json").unwrap_or(false))
            .collect();
        entries.sort_by_key(|e| {
            e.metadata()
                .ok()
                .and_then(|m| m.modified().ok())
                .unwrap_or(std::time::UNIX_EPOCH)
        });
        entries.last().map(|e| e.path())
    }
}

impl Workspace {
    pub fn base_dir_path() -> PathBuf {
        dirs::home_dir()
            .expect("Failed to get home dir")
            .join(".sheetgo")
    }

    /// 初始化工作区（首次运行创建目录结构）
    pub fn init() -> Result<Self, String> {
        let base_dir = Self::base_dir_path();
        fs::create_dir_all(&base_dir).map_err(|e| e.to_string())?;
        Ok(Workspace { base_dir })
    }

    /// 创建新的会话工作区
    pub fn create_session(&self, session_id: &str) -> Result<SessionWorkspace, String> {
        let base = self.base_dir.join("workspace").join(session_id);
        let source = base.join("source");
        let working = base.join("working");
        let cache = base.join("cache");
        let snapshots = base.join("snapshots");
        let exports = base.join("exports");

        fs::create_dir_all(&source).map_err(|e| e.to_string())?;
        fs::create_dir_all(&working).map_err(|e| e.to_string())?;
        fs::create_dir_all(&cache).map_err(|e| e.to_string())?;
        fs::create_dir_all(&snapshots).map_err(|e| e.to_string())?;
        fs::create_dir_all(&exports).map_err(|e| e.to_string())?;

        Ok(SessionWorkspace {
            base_dir: base,
            source_dir: source,
            working_dir: working,
            cache_dir: cache,
            snapshot_dir: snapshots,
            export_dir: exports,
        })
    }

    /// 获取会话工作区
    pub fn get_session(&self, session_id: &str) -> Result<SessionWorkspace, String> {
        let base = self.base_dir.join("workspace").join(session_id);
        if !base.exists() {
            return self.create_session(session_id);
        }
        Ok(SessionWorkspace {
            source_dir: base.join("source"),
            working_dir: base.join("working"),
            cache_dir: base.join("cache"),
            snapshot_dir: base.join("snapshots"),
            export_dir: base.join("exports"),
            base_dir: base,
        })
    }

    /// 清理过期会话
    pub fn cleanup(&self, max_age_days: u32) -> Result<(), String> {
        let workspace_dir = self.base_dir.join("workspace");
        if !workspace_dir.exists() {
            return Ok(());
        }
        let max_age = std::time::Duration::from_secs(max_age_days as u64 * 86400);
        let now = std::time::SystemTime::now();

        for entry in fs::read_dir(&workspace_dir).map_err(|e| e.to_string())? {
            let entry = entry.map_err(|e| e.to_string())?;
            if let Ok(meta) = entry.metadata() {
                if let Ok(modified) = meta.modified() {
                    if now.duration_since(modified).unwrap_or_default() > max_age {
                        let _ = fs::remove_dir_all(entry.path());
                    }
                }
            }
        }
        Ok(())
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_workspace_init() {
        let ws = Workspace::init();
        assert!(ws.is_ok());
        let ws = ws.unwrap();
        assert!(ws.base_dir.exists());
    }

    #[test]
    fn test_create_session() {
        let ws = Workspace::init().unwrap();
        let session_id = "test_session_001";
        let session = ws.create_session(session_id).unwrap();
        assert!(session.source_dir.exists());
        assert!(session.working_dir.exists());
        assert!(session.cache_dir.exists());
        assert!(session.snapshot_dir.exists());
        assert!(session.export_dir.exists());
        let _ = fs::remove_dir_all(&session.base_dir);
    }

    #[test]
    fn test_get_session_auto_create() {
        let ws = Workspace::init().unwrap();
        let session_id = "test_session_002";
        let session = ws.get_session(session_id).unwrap();
        assert!(session.source_dir.exists());
        let _ = fs::remove_dir_all(&session.base_dir);
    }

    #[test]
    fn test_import_file() {
        let ws = Workspace::init().unwrap();
        let session = ws.create_session("test_session_003").unwrap();
        let tmp = std::env::temp_dir().join("test_sheetgo.xlsx");
        fs::write(&tmp, b"fake xlsx data").unwrap();
        let file_id = session.import_file(&tmp).unwrap();
        assert!(!file_id.is_empty());
        let imported = session.source_dir.join(format!("{}.xlsx", file_id));
        assert!(imported.exists());
        let _ = fs::remove_file(&tmp);
        let _ = fs::remove_dir_all(&session.base_dir);
    }
}
