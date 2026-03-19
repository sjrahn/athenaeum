use std::collections::{BTreeMap, BTreeSet, HashSet};

use crate::model::{Record, RecordType, Status};

/// Filter criteria for records.
#[derive(Debug, Default)]
pub struct RecordFilter {
    pub search_text: String,
    pub record_types: HashSet<RecordType>,
    pub content_types: HashSet<String>,
    pub statuses: HashSet<Status>,
    pub credibility_tiers: HashSet<String>,
    pub tags: HashSet<String>,
    pub origin_names: HashSet<String>,
    pub has_unresolved_issues: Option<bool>,
}

impl RecordFilter {
    /// Returns true if all filter criteria are empty (no filtering active).
    pub fn is_empty(&self) -> bool {
        self.search_text.is_empty()
            && self.record_types.is_empty()
            && self.content_types.is_empty()
            && self.statuses.is_empty()
            && self.credibility_tiers.is_empty()
            && self.tags.is_empty()
            && self.origin_names.is_empty()
            && self.has_unresolved_issues.is_none()
    }

    /// Check whether a record matches all active filter criteria.
    pub fn matches(&self, record: &Record) -> bool {
        let fm = &record.frontmatter;

        // Text search: matches title, description, or tags (case-insensitive)
        if !self.search_text.is_empty() {
            let q = self.search_text.to_lowercase();
            let text_match = fm.title.to_lowercase().contains(&q)
                || fm.description.to_lowercase().contains(&q)
                || fm.tags.iter().any(|t| t.to_lowercase().contains(&q));
            if !text_match {
                return false;
            }
        }

        if !self.record_types.is_empty() && !self.record_types.contains(&fm.record_type) {
            return false;
        }

        if !self.content_types.is_empty() && !self.content_types.contains(&fm.content_type) {
            return false;
        }

        if !self.statuses.is_empty() && !self.statuses.contains(&fm.status) {
            return false;
        }

        if !self.credibility_tiers.is_empty() {
            match &fm.credibility_tier {
                Some(tier) if self.credibility_tiers.contains(tier) => {}
                _ => return false,
            }
        }

        if !self.tags.is_empty() && !self.tags.iter().any(|t| fm.tags.contains(t)) {
            return false;
        }

        if !self.origin_names.is_empty() {
            match &fm.origin_name {
                Some(name) if self.origin_names.contains(name) => {}
                _ => return false,
            }
        }

        if let Some(want_unresolved) = self.has_unresolved_issues {
            let has = fm.issues.iter().any(|i| !i.resolved);
            if has != want_unresolved {
                return false;
            }
        }

        true
    }
}

/// How to group records in the sidebar.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum GroupBy {
    ContentType,
    Status,
    CredibilityTier,
    OriginName,
    Tag,
    RecordType,
}

/// Group records by a field, returning groups in sorted order.
pub fn group_records<'a>(
    records: impl Iterator<Item = &'a Record>,
    group_by: GroupBy,
) -> BTreeMap<String, Vec<&'a Record>> {
    let mut groups: BTreeMap<String, Vec<&'a Record>> = BTreeMap::new();

    for record in records {
        let fm = &record.frontmatter;
        let keys: Vec<String> = match group_by {
            GroupBy::ContentType => vec![fm.content_type.clone()],
            GroupBy::Status => vec![fm.status.to_string()],
            GroupBy::CredibilityTier => {
                vec![fm
                    .credibility_tier
                    .clone()
                    .unwrap_or_else(|| "unknown".to_string())]
            }
            GroupBy::OriginName => {
                vec![fm
                    .origin_name
                    .clone()
                    .unwrap_or_else(|| "unknown".to_string())]
            }
            GroupBy::Tag => {
                if fm.tags.is_empty() {
                    vec!["untagged".to_string()]
                } else {
                    fm.tags.clone()
                }
            }
            GroupBy::RecordType => vec![fm.record_type.to_string()],
        };

        for key in keys {
            groups.entry(key).or_default().push(record);
        }
    }

    groups
}

/// Compute facets from a collection of records for populating filter dropdowns.
pub struct Facets {
    pub all_tags: BTreeSet<String>,
    pub all_content_types: BTreeSet<String>,
    pub all_origin_names: BTreeSet<String>,
    pub all_credibility_tiers: BTreeSet<String>,
}

impl Facets {
    pub fn compute<'a>(records: impl Iterator<Item = &'a Record>) -> Self {
        let mut facets = Facets {
            all_tags: BTreeSet::new(),
            all_content_types: BTreeSet::new(),
            all_origin_names: BTreeSet::new(),
            all_credibility_tiers: BTreeSet::new(),
        };

        for record in records {
            let fm = &record.frontmatter;
            facets.all_content_types.insert(fm.content_type.clone());
            for tag in &fm.tags {
                facets.all_tags.insert(tag.clone());
            }
            if let Some(name) = &fm.origin_name {
                facets.all_origin_names.insert(name.clone());
            }
            if let Some(tier) = &fm.credibility_tier {
                facets.all_credibility_tiers.insert(tier.clone());
            }
        }

        facets
    }
}
