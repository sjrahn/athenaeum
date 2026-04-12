use std::sync::{Arc, Mutex};

use ath_core::api_types::{CorpusInfo, FacetsResponse, QueryResult, RecordDetail};

use crate::state::AppState;
use crate::views;

/// Pending HTTP responses, polled each frame.
#[derive(Default)]
struct PendingRequests {
    corpora: Option<Result<Vec<CorpusInfo>, String>>,
    facets: Option<Result<FacetsResponse, String>>,
    records: Option<Result<QueryResult, String>>,
    detail: Option<Result<Option<RecordDetail>, String>>,
}

enum LoadState {
    Loading,
    Ready,
    Error(String),
}

pub struct AtheneumApp {
    pub state: AppState,
    load_state: LoadState,
    server_url: String,
    pending: Arc<Mutex<PendingRequests>>,
    /// Track whether a records request is in flight to avoid duplicate requests.
    records_request_in_flight: bool,
    detail_request_in_flight: bool,
}

impl AtheneumApp {
    pub fn new(server_url: String) -> Self {
        let mut app = AtheneumApp {
            state: AppState::new(),
            load_state: LoadState::Loading,
            server_url,
            pending: Arc::new(Mutex::new(PendingRequests::default())),
            records_request_in_flight: false,
            detail_request_in_flight: false,
        };
        app.fetch_corpora();
        app
    }

    fn fetch_corpora(&mut self) {
        let url = format!("{}/api/corpora", self.server_url);
        let pending = self.pending.clone();

        ehttp::fetch(ehttp::Request::get(&url), move |result| {
            let outcome = parse_response::<Vec<CorpusInfo>>(result);
            pending.lock().unwrap().corpora = Some(outcome);
        });
    }

    fn fetch_facets(&mut self) {
        let corpus = self.state.corpus_name().to_owned();
        let url = format!(
            "{}/api/facets?corpus={}",
            self.server_url,
            url_encode(&corpus)
        );
        let pending = self.pending.clone();

        ehttp::fetch(ehttp::Request::get(&url), move |result| {
            let outcome = parse_response::<FacetsResponse>(result);
            pending.lock().unwrap().facets = Some(outcome);
        });
    }

    pub fn fetch_records(&mut self) {
        if self.records_request_in_flight || self.state.corpora.is_empty() {
            return;
        }
        self.records_request_in_flight = true;

        let url = self.state.build_records_url(&self.server_url);
        let pending = self.pending.clone();

        ehttp::fetch(ehttp::Request::get(&url), move |result| {
            let outcome = parse_response::<QueryResult>(result);
            pending.lock().unwrap().records = Some(outcome);
        });
    }

    pub fn fetch_detail(&mut self, uuid: uuid::Uuid) {
        if self.detail_request_in_flight {
            return;
        }
        self.detail_request_in_flight = true;

        let url = format!("{}/api/records/{}", self.server_url, uuid);
        let pending = self.pending.clone();

        ehttp::fetch(ehttp::Request::get(&url), move |result| {
            let outcome = parse_response::<Option<RecordDetail>>(result);
            pending.lock().unwrap().detail = Some(outcome);
        });
    }
}

impl eframe::App for AtheneumApp {
    fn update(&mut self, ctx: &egui::Context, _frame: &mut eframe::Frame) {
        // Poll pending responses
        {
            let mut pending = self.pending.lock().unwrap();

            // Corpora list
            if let Some(result) = pending.corpora.take() {
                match result {
                    Ok(corpora) => {
                        tracing::info!(count = corpora.len(), "loaded corpora list");
                        self.state.corpora = corpora;
                        self.load_state = LoadState::Ready;
                        // Auto-fetch facets and records for first corpus
                        drop(pending);
                        self.fetch_facets();
                        self.fetch_records();
                        // Re-acquire for remaining checks
                        pending = self.pending.lock().unwrap();
                    }
                    Err(e) => {
                        tracing::error!(%e, "failed to fetch corpora");
                        self.state.load_error = Some(e.clone());
                        self.load_state = LoadState::Error(e);
                    }
                }
            }

            // Facets
            if let Some(result) = pending.facets.take() {
                match result {
                    Ok(facets) => self.state.facets = Some(facets),
                    Err(e) => tracing::warn!(%e, "failed to fetch facets"),
                }
            }

            // Records
            if let Some(result) = pending.records.take() {
                self.records_request_in_flight = false;
                match result {
                    Ok(query_result) => {
                        self.state.sidebar_total = query_result.total;
                        self.state.sidebar_entries = query_result.records;
                    }
                    Err(e) => tracing::warn!(%e, "failed to fetch records"),
                }
            }

            // Record detail
            if let Some(result) = pending.detail.take() {
                self.detail_request_in_flight = false;
                match result {
                    Ok(detail) => self.state.selected_detail = detail,
                    Err(e) => tracing::warn!(%e, "failed to fetch record detail"),
                }
            }
        }

        // Loading screen
        if matches!(self.load_state, LoadState::Loading) {
            egui::CentralPanel::default().show(ctx, |ui| {
                ui.centered_and_justified(|ui| {
                    ui.heading("Loading corpora...");
                });
            });
            ctx.request_repaint();
            return;
        }

        // Top panel: filter bar
        egui::TopBottomPanel::top("filter_bar").show(ctx, |ui| {
            let action = views::filter_bar(ui, &mut self.state);
            match action {
                views::FilterAction::None => {}
                views::FilterAction::SwitchCorpus(idx) => {
                    self.state.active_corpus_idx = idx;
                    self.state.selected_record = None;
                    self.state.selected_detail = None;
                    self.state.search_text.clear();
                    self.state.filter_content_type = None;
                    self.state.filter_status = None;
                    self.state.filter_tag = None;
                    self.state.filter_origin_name = None;
                    self.state.filter_credibility_tier = None;
                    self.state.filter_record_type = None;
                    self.state.facets = None; // clear stale facets
                    self.state.sidebar_entries.clear();
                    self.state.sidebar_total = 0;
                    self.fetch_facets();
                    self.fetch_records();
                }
                views::FilterAction::RefreshRecords => {
                    self.fetch_records();
                }
            }
        });

        // Bottom panel: status bar
        egui::TopBottomPanel::bottom("status_bar").show(ctx, |ui| {
            views::status_bar(ui, &self.state);
        });

        // Left panel: sidebar
        egui::SidePanel::left("sidebar")
            .default_width(320.0)
            .resizable(true)
            .show(ctx, |ui| {
                if let Some(uuid) = views::sidebar(ui, &mut self.state) {
                    self.fetch_detail(uuid);
                }
            });

        // Central panel: detail view
        egui::CentralPanel::default().show(ctx, |ui| {
            views::detail_view(ui, &mut self.state);
        });

        // If a navigation link was clicked in detail view, fetch the new record
        if let Some(uuid) = self.state.selected_record {
            if self.state.selected_detail.is_none() && !self.detail_request_in_flight {
                self.fetch_detail(uuid);
            }
        }
    }
}

fn parse_response<T: serde::de::DeserializeOwned>(
    result: Result<ehttp::Response, String>,
) -> Result<T, String> {
    match result {
        Ok(response) if response.ok => serde_json::from_slice(&response.bytes)
            .map_err(|e| format!("Failed to parse response: {e}")),
        Ok(response) => Err(format!(
            "Server error: {} {}",
            response.status, response.status_text
        )),
        Err(e) => Err(e),
    }
}

fn url_encode(s: &str) -> String {
    s.replace('%', "%25")
        .replace(' ', "%20")
        .replace('&', "%26")
        .replace('=', "%3D")
        .replace('#', "%23")
        .replace('+', "%2B")
}
