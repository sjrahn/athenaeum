use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum RecordType {
    Source,
    Document,
}

impl std::fmt::Display for RecordType {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            Self::Source => write!(f, "source"),
            Self::Document => write!(f, "document"),
        }
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum Status {
    Stub,
    Draft,
    Normalized,
}

impl std::fmt::Display for Status {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            Self::Stub => write!(f, "stub"),
            Self::Draft => write!(f, "draft"),
            Self::Normalized => write!(f, "normalized"),
        }
    }
}

/// Known credibility tiers from the spec. Stored as String in frontmatter
/// to tolerate stubs that use "pending".
pub const CREDIBILITY_TIERS: &[&str] = &[
    "authoritative",
    "expert",
    "community_validated",
    "anecdotal",
    "speculative",
];
