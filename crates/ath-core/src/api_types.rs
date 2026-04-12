//! Shared API types used by both server and GUI.

use serde::{Deserialize, Serialize};
use uuid::Uuid;

use crate::model::Record;

/// Lightweight corpus info for listing.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct CorpusInfo {
    pub name: String,
    pub record_count: u64,
}

/// Query parameters for searching/filtering records.
#[derive(Debug, Default, Deserialize)]
pub struct QueryParams {
    pub corpus: String,
    #[serde(default)]
    pub q: String,
    #[serde(default = "default_sort")]
    pub sort: String,
    #[serde(default)]
    pub offset: u64,
    #[serde(default = "default_limit")]
    pub limit: u64,
    #[serde(default)]
    pub content_type: Option<String>,
    #[serde(default)]
    pub status: Option<String>,
    #[serde(default)]
    pub tag: Option<String>,
    #[serde(default)]
    pub origin_name: Option<String>,
    #[serde(default)]
    pub credibility_tier: Option<String>,
    #[serde(default)]
    pub record_type: Option<String>,
}

fn default_sort() -> String {
    "title_asc".to_string()
}

fn default_limit() -> u64 {
    100
}

/// A lightweight record summary for sidebar display (no body).
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct RecordSummary {
    pub uuid: Uuid,
    pub title: String,
    pub status: String,
    pub content_type: String,
    pub record_type: String,
    pub tags: Vec<String>,
}

/// Paginated query result.
#[derive(Debug, Serialize, Deserialize)]
pub struct QueryResult {
    pub total: u64,
    pub records: Vec<RecordSummary>,
}

/// Full record detail with parent/child relationships.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct RecordDetail {
    pub record: Record,
    pub parents: Vec<RecordSummary>,
    pub children: Vec<RecordSummary>,
}

/// Available facet values for filter dropdowns.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct FacetsResponse {
    pub content_types: Vec<String>,
    pub statuses: Vec<String>,
    pub tags: Vec<String>,
    pub origin_names: Vec<String>,
    pub credibility_tiers: Vec<String>,
}

/// Response after a successful capture submission.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SubmitResponse {
    pub folder: String,
    pub file_count: u32,
}

/// A single pending capture folder in the submission queue.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SubmissionEntry {
    pub folder: String,
    pub title: String,
    pub url: Option<String>,
    pub source_type: Option<String>,
    pub capture_date: String,
    pub files: Vec<String>,
}

/// Response listing all pending capture folders.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SubmissionsResponse {
    pub submissions: Vec<SubmissionEntry>,
}
