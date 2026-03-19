use ath_core::corpus::Corpus;
use ath_core::dag::RecordDag;
use ath_core::filter::{Facets, GroupBy, RecordFilter};
use uuid::Uuid;

/// Sort order for the sidebar record list.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum SortOrder {
    TitleAsc,
    TitleDesc,
    StatusAsc,
}

/// All mutable application state.
pub struct AppState {
    // Data
    pub corpus: Corpus,
    pub dag: RecordDag,

    // Facets (computed from corpus)
    pub facets: Facets,

    // UI state
    pub selected_record: Option<Uuid>,
    pub filter: RecordFilter,
    pub group_by: Option<GroupBy>,
    pub sort_order: SortOrder,

    // Derived: sorted/filtered list of UUIDs for the sidebar
    pub filtered_uuids: Vec<Uuid>,

    // Status
    pub load_error: Option<String>,
}

impl AppState {
    pub fn new(corpus: Corpus) -> Self {
        let dag = RecordDag::build(&corpus.records);
        let facets = Facets::compute(corpus.records.values());
        let mut state = AppState {
            corpus,
            dag,
            facets,
            selected_record: None,
            filter: RecordFilter::default(),
            group_by: None,
            sort_order: SortOrder::TitleAsc,
            filtered_uuids: Vec::new(),
            load_error: None,
        };
        state.recompute_filtered_list();
        state
    }

    /// Recompute the filtered and sorted list of record UUIDs.
    pub fn recompute_filtered_list(&mut self) {
        let mut uuids: Vec<Uuid> = self
            .corpus
            .records
            .values()
            .filter(|r| self.filter.is_empty() || self.filter.matches(r))
            .map(|r| r.frontmatter.uuid)
            .collect();

        // Sort
        let records = &self.corpus.records;
        match self.sort_order {
            SortOrder::TitleAsc => {
                uuids.sort_by(|a, b| {
                    let ta = records.get(a).map(|r| r.frontmatter.title.as_str()).unwrap_or("");
                    let tb = records.get(b).map(|r| r.frontmatter.title.as_str()).unwrap_or("");
                    ta.to_lowercase().cmp(&tb.to_lowercase())
                });
            }
            SortOrder::TitleDesc => {
                uuids.sort_by(|a, b| {
                    let ta = records.get(a).map(|r| r.frontmatter.title.as_str()).unwrap_or("");
                    let tb = records.get(b).map(|r| r.frontmatter.title.as_str()).unwrap_or("");
                    tb.to_lowercase().cmp(&ta.to_lowercase())
                });
            }
            SortOrder::StatusAsc => {
                uuids.sort_by(|a, b| {
                    let sa = records.get(a).map(|r| r.frontmatter.status as u8).unwrap_or(0);
                    let sb = records.get(b).map(|r| r.frontmatter.status as u8).unwrap_or(0);
                    sa.cmp(&sb)
                });
            }
        }

        self.filtered_uuids = uuids;
    }

    /// Recompute facets from the current corpus.
    pub fn recompute_facets(&mut self) {
        self.facets = Facets::compute(self.corpus.records.values());
    }

    /// Get all unique tags in sorted order (convenience for UI).
    pub fn all_tags_sorted(&self) -> Vec<&str> {
        self.facets.all_tags.iter().map(|s| s.as_str()).collect()
    }
}
