use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Issue {
    #[serde(rename = "type")]
    pub issue_type: String,
    pub severity: String,
    pub description: String,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub remediation: Option<String>,
    #[serde(default)]
    pub resolved: bool,
}

/// Known issue types from the spec.
pub const ISSUE_TYPES: &[&str] = &[
    "missing_media",
    "broken_links",
    "partial_content",
    "content_modified",
    "encoding_corruption",
    "format_loss",
];

/// Known severity levels.
pub const SEVERITIES: &[&str] = &["critical", "major", "minor"];

/// Known remediation strategies.
pub const REMEDIATIONS: &[&str] = &[
    "wayback_snapshot",
    "alternate_source",
    "original_author",
    "re_capture",
    "manual_reconstruction",
    "none",
];
