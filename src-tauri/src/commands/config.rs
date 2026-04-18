use crate::workspace::Workspace;
use serde::{Deserialize, Serialize};
use std::fs;
use std::path::PathBuf;

#[derive(Serialize, Deserialize, Debug, Clone)]
#[serde(rename_all = "camelCase")]
pub struct LlmConfig {
    pub provider: String,
    pub model: String,
    pub api_key: String,
    pub base_url: String,
    pub temperature: f64,
    pub max_tokens: u32,
}

#[derive(Serialize, Deserialize, Debug, Clone)]
#[serde(rename_all = "camelCase")]
pub struct UiConfig {
    pub theme: String,
    #[serde(default = "default_theme_preset")]
    pub theme_preset: String,
    pub language: String,
    pub preview_rows: u32,
}

fn default_theme_preset() -> String {
    "default".to_string()
}

#[derive(Serialize, Deserialize, Debug, Clone)]
#[serde(rename_all = "camelCase")]
pub struct AdvancedConfig {
    pub max_file_size: u64,
    pub preload_sample_rows: u32,
    pub snapshot_max_count: u32,
    pub sandbox_enabled: bool,
}

#[derive(Serialize, Deserialize, Debug, Clone)]
#[serde(rename_all = "camelCase")]
pub struct AppConfig {
    pub llm: LlmConfig,
    pub ui: UiConfig,
    pub advanced: AdvancedConfig,
}

impl Default for AppConfig {
    fn default() -> Self {
        AppConfig {
            llm: LlmConfig {
                provider: "openai".to_string(),
                model: "gpt-4o".to_string(),
                api_key: "".to_string(),
                base_url: "".to_string(),
                temperature: 0.1,
                max_tokens: 4096,
            },
            ui: UiConfig {
                theme: "light".to_string(),
                theme_preset: default_theme_preset(),
                language: "zh-CN".to_string(),
                preview_rows: 100,
            },
            advanced: AdvancedConfig {
                max_file_size: 104857600,
                preload_sample_rows: 20,
                snapshot_max_count: 50,
                sandbox_enabled: true,
            },
        }
    }
}

fn config_path() -> PathBuf {
    Workspace::base_dir_path().join("config.json")
}

#[tauri::command]
pub async fn get_config() -> Result<AppConfig, String> {
    let path = config_path();
    if path.exists() {
        let content = fs::read_to_string(&path).map_err(|e| e.to_string())?;
        let config: AppConfig = serde_json::from_str(&content).map_err(|e| e.to_string())?;
        Ok(config)
    } else {
        Ok(AppConfig::default())
    }
}

#[tauri::command]
pub async fn save_config(config: AppConfig) -> Result<(), String> {
    let path = config_path();
    let content = serde_json::to_string_pretty(&config).map_err(|e| e.to_string())?;
    fs::write(&path, content).map_err(|e| e.to_string())?;
    Ok(())
}
