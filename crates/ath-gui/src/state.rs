use ath_core::api_types::{CorpusInfo, FacetsResponse, RecordDetail, RecordSummary};
use uuid::Uuid;

/// Sort order for the sidebar record list.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum SortOrder {
    TitleAsc,
    TitleDesc,
    StatusAsc,
    NewestFirst,
}

impl SortOrder {
    pub fn as_query_param(&self) -> &str {
        match self {
            SortOrder::TitleAsc => "title_asc",
            SortOrder::TitleDesc => "title_desc",
            SortOrder::StatusAsc => "status_asc",
            SortOrder::NewestFirst => "newest_first",
        }
    }
}

/// All mutable application state — thin client backed by server queries.
pub struct AppState {
    // Corpus list
    pub corpora: Vec<CorpusInfo>,
    pub active_corpus_idx: usize,

    // Facets for filter dropdowns
    pub facets: Option<FacetsResponse>,

    // Sidebar data (paginated from server)
    pub sidebar_entries: Vec<RecordSummary>,
    pub sidebar_total: u64,

    // Selected record detail
    pub selected_record: Option<Uuid>,
    pub selected_detail: Option<RecordDetail>,

    // Filter/search state
    pub search_text: String,
    pub sort_order: SortOrder,
    pub filter_content_type: Option<String>,
    pub filter_status: Option<String>,
    pub filter_tag: Option<String>,
    pub filter_origin_name: Option<String>,
    pub filter_credibility_tier: Option<String>,
    pub filter_record_type: Option<String>,

    // Status
    pub load_error: Option<String>,
}

impl AppState {
    pub fn new() -> Self {
        AppState {
            corpora: Vec::new(),
            active_corpus_idx: 0,
            facets: None,
            sidebar_entries: Vec::new(),
            sidebar_total: 0,
            selected_record: None,
            selected_detail: None,
            search_text: String::new(),
            sort_order: SortOrder::TitleAsc,
            filter_content_type: None,
            filter_status: None,
            filter_tag: None,
            filter_origin_name: None,
            filter_credibility_tier: None,
            filter_record_type: None,
            load_error: None,
        }
    }

    /// Get the active corpus name, if any.
    pub fn corpus_name(&self) -> &str {
        self.corpora
            .get(self.active_corpus_idx)
            .map(|c| c.name.as_str())
            .unwrap_or("")
    }

    /// Build query string for the records API.
    pub fn build_records_url(&self, server_url: &str) -> String {
        let corpus = self.corpus_name();
        let mut url = format!(
            "{}/api/records?corpus={}&sort={}&offset=0&limit=10000",
            server_url,
            url_encode(corpus),
            self.sort_order.as_query_param(),
        );

        if !self.search_text.is_empty() {
            url.push_str(&format!("&q={}", url_encode(&self.search_text)));
        }

        if let Some(ct) = &self.filter_content_type {
            url.push_str(&format!("&content_type={}", url_encode(ct)));
        }

        if let Some(st) = &self.filter_status {
            url.push_str(&format!("&status={}", url_encode(st)));
        }

        if let Some(tag) = &self.filter_tag {
            url.push_str(&format!("&tag={}", url_encode(tag)));
        }

        if let Some(on) = &self.filter_origin_name {
            url.push_str(&format!("&origin_name={}", url_encode(on)));
        }

        if let Some(ct) = &self.filter_credibility_tier {
            url.push_str(&format!("&credibility_tier={}", url_encode(ct)));
        }

        if let Some(rt) = &self.filter_record_type {
            url.push_str(&format!("&record_type={}", url_encode(rt)));
        }

        url
    }
}

/// Minimal URL encoding for query parameters.
fn url_encode(s: &str) -> String {
    s.replace('%', "%25")
        .replace(' ', "%20")
        .replace('&', "%26")
        .replace('=', "%3D")
        .replace('#', "%23")
        .replace('+', "%2B")
}
