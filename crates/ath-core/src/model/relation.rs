use serde::{Deserialize, Serialize};
use uuid::Uuid;

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Relation {
    #[serde(rename = "type")]
    pub relation_type: String,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub target: Option<Uuid>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub unresolved: Option<String>,
}

/// Known relation types from the spec.
pub const RELATION_TYPES: &[&str] = &[
    "sequel_to",
    "preceded_by",
    "reply_to",
    "references",
    "adaptation_of",
    "supersedes",
    "superseded_by",
    "contradicts",
];
