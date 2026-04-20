use std::collections::BTreeMap;

use chrono::NaiveDate;
use serde::{Deserialize, Serialize};
use uuid::Uuid;

use super::{ArtifactRef, AssetRef, Issue, RecordType, Status};

/// Deserializer that accepts a NaiveDate or returns None for non-date strings
/// like "pending".
fn deserialize_optional_date<'de, D>(deserializer: D) -> Result<Option<NaiveDate>, D::Error>
where
    D: serde::Deserializer<'de>,
{
    use serde::de::Error;

    let value: serde_yaml_ng::Value = Deserialize::deserialize(deserializer)?;
    match &value {
        serde_yaml_ng::Value::Null => Ok(None),
        serde_yaml_ng::Value::String(s) => {
            if s == "pending" || s.is_empty() {
                Ok(None)
            } else {
                // Try bare date first, then datetime (extract date portion)
                NaiveDate::parse_from_str(s, "%Y-%m-%d")
                    .or_else(|_| {
                        chrono::NaiveDateTime::parse_from_str(s, "%Y-%m-%dT%H:%M:%S%Z")
                            .or_else(|_| chrono::NaiveDateTime::parse_from_str(s, "%Y-%m-%dT%H:%M:%S"))
                            .map(|dt| dt.date())
                    })
                    .or_else(|_| {
                        // Try parsing as RFC 3339 / ISO 8601 with timezone
                        s.parse::<chrono::DateTime<chrono::Utc>>()
                            .map(|dt| dt.date_naive())
                            .map_err(|e| e.into())
                    })
                    .map(Some)
                    .map_err(|e: chrono::ParseError| D::Error::custom(format!("invalid date '{s}': {e}")))
            }
        }
        // serde_yaml_ng may parse dates as tagged values
        _ => {
            // Try converting via the YAML value's string representation
            let s = format!("{value:?}");
            // Fall back to treating as a date string
            serde_yaml_ng::from_value::<NaiveDate>(value)
                .map(Some)
                .map_err(|e| D::Error::custom(format!("invalid date '{s}': {e}")))
        }
    }
}

fn serialize_optional_date<S>(date: &Option<NaiveDate>, serializer: S) -> Result<S::Ok, S::Error>
where
    S: serde::Serializer,
{
    match date {
        Some(d) => serializer.serialize_str(&d.format("%Y-%m-%d").to_string()),
        None => serializer.serialize_none(),
    }
}

/// Frontmatter for all Athenaeum records.
///
/// Core fields are strongly typed. Content-type-specific extended fields
/// are captured in the `extended` BTreeMap via `#[serde(flatten)]`.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Frontmatter {
    // --- Core fields (all records) ---
    pub uuid: Uuid,
    pub title: String,
    pub description: String,
    pub record_type: RecordType,
    #[serde(default, alias = "source_type")]
    pub content_type: String,
    pub status: Status,
    #[serde(default, skip_serializing_if = "Vec::is_empty")]
    pub tags: Vec<String>,
    /// Editorial curation layer (independent from pipeline `status`).
    /// `"visible"` (default) | `"deranked"` | `"hidden"`. Absent == visible.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub visibility: Option<String>,

    // --- Quality fields ---
    /// Stored as String to tolerate "pending" in stubs.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub credibility_tier: Option<String>,
    #[serde(default)]
    pub normalization_confidence: f64,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub normalization_model: Option<String>,
    #[serde(
        default,
        deserialize_with = "deserialize_optional_date",
        serialize_with = "serialize_optional_date",
        skip_serializing_if = "Option::is_none"
    )]
    pub normalization_date: Option<NaiveDate>,

    // --- Source-specific fields ---
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub origin_url: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub origin_name: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub original_filename: Option<String>,
    #[serde(
        default,
        deserialize_with = "deserialize_optional_date",
        serialize_with = "serialize_optional_date",
        skip_serializing_if = "Option::is_none"
    )]
    pub capture_date: Option<NaiveDate>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub artifact_store: Option<String>,
    #[serde(default, skip_serializing_if = "Vec::is_empty")]
    pub artifact_refs: Vec<ArtifactRef>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub author: Option<String>,
    #[serde(
        default,
        deserialize_with = "deserialize_optional_date",
        serialize_with = "serialize_optional_date",
        skip_serializing_if = "Option::is_none"
    )]
    pub date_published: Option<NaiveDate>,

    // --- Document-specific fields ---
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub constituents: Option<Vec<Uuid>>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub merge_rationale: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub asset_store: Option<String>,
    #[serde(default, skip_serializing_if = "Vec::is_empty")]
    pub asset_refs: Vec<AssetRef>,

    // --- Pipeline fields ---
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub conversion_method: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub conversion_tool: Option<String>,
    #[serde(
        default,
        deserialize_with = "deserialize_optional_date",
        serialize_with = "serialize_optional_date",
        skip_serializing_if = "Option::is_none"
    )]
    pub conversion_date: Option<NaiveDate>,

    // --- Issues and relations ---
    #[serde(default, skip_serializing_if = "Vec::is_empty")]
    pub issues: Vec<Issue>,
    /// Set-theory classification: "this record is an instance of the concept
    /// described by each target". Instance → concept only.
    #[serde(default, skip_serializing_if = "Vec::is_empty")]
    pub part_of: Vec<Uuid>,
    /// Identity equivalence (reuploads, re-captures, dedup). Symmetric.
    #[serde(default, skip_serializing_if = "Vec::is_empty")]
    pub same_as: Vec<Uuid>,

    // --- Extended fields (content-type-specific) ---
    /// Captures all fields not explicitly modeled above.
    #[serde(flatten)]
    pub extended: BTreeMap<String, serde_yaml_ng::Value>,
}
