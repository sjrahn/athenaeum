use serde::{Deserialize, Serialize};
use uuid::Uuid;

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ArtifactRef {
    #[serde(rename = "ref")]
    pub uri: String,
    pub sha256: String,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub mimetype: Option<String>,
    #[serde(default, skip_serializing_if = "std::ops::Not::not")]
    pub primary: bool,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AssetRef {
    #[serde(rename = "ref")]
    pub uri: String,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub sha256: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub source: Option<Uuid>,
}
