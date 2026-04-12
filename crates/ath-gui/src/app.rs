use std::collections::BTreeMap;
use std::sync::{Arc, Mutex};

use ath_core::api_types::{CorpusInfo, FacetsResponse, QueryResult, RecordDetail};
use uuid::Uuid;

use crate::state::AppState;
use crate::views;

/// Pending HTTP responses, polled each frame.
#[derive(Default)]
struct PendingRequests {
    corpora: Option<Result<Vec<CorpusInfo>, String>>,
    facets: Option<Result<FacetsResponse, String>>,
    records: Option<Result<QueryResult, String>>,
    /// Detail responses keyed by UUID (supports multiple in-flight window fetches).
    details: BTreeMap<Uuid, Result<Option<RecordDetail>, String>>,
}

enum LoadState {
    Loading,
    Ready,
    Error,
}

pub struct AtheneumApp {
    pub state: AppState,
    load_state: LoadState,
    server_url: String,
    pending: Arc<Mutex<PendingRequests>>,
    records_request_in_flight: bool,
    details_in_flight: std::collections::BTreeSet<Uuid>,
}

impl AtheneumApp {
    pub fn new(server_url: String) -> Self {
        let mut app = AtheneumApp {
            state: AppState::new(),
            load_state: LoadState::Loading,
            server_url,
            pending: Arc::new(Mutex::new(PendingRequests::default())),
            records_request_in_flight: false,
            details_in_flight: std::collections::BTreeSet::new(),
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

    pub fn fetch_detail(&mut self, uuid: Uuid) {
        if self.details_in_flight.contains(&uuid) {
            return;
        }
        self.details_in_flight.insert(uuid);

        let url = format!("{}/api/records/{}", self.server_url, uuid);
        let pending = self.pending.clone();

        ehttp::fetch(ehttp::Request::get(&url), move |result| {
            let outcome = parse_response::<Option<RecordDetail>>(result);
            pending.lock().unwrap().details.insert(uuid, outcome);
        });
    }

    fn switch_corpus(&mut self, idx: usize) {
        self.state.active_corpus_idx = idx;
        self.state.open_windows.clear();
        self.state.search_text.clear();
        self.state.filter_content_type = None;
        self.state.filter_status = None;
        self.state.filter_tag = None;
        self.state.filter_origin_name = None;
        self.state.filter_credibility_tier = None;
        self.state.filter_record_type = None;
        self.state.facets = None;
        self.state.sidebar_entries.clear();
        self.state.sidebar_total = 0;
        self.fetch_facets();
        self.fetch_records();
    }

    fn menu_bar(&mut self, ui: &mut egui::Ui) {
        egui::MenuBar::new().ui(ui, |ui| {
            ui.menu_button("File", |ui| {
                if ui.button("Close All Windows").clicked() {
                    self.state.open_windows.clear();
                    ui.close();
                }
            });

            ui.menu_button("View", |ui| {
                ui.checkbox(&mut self.state.show_sidebar, "Sidebar");
                ui.checkbox(&mut self.state.show_filter_bar, "Filter Bar");
            });

            // Corpus switcher in menu bar
            let corpus_label = if self.state.corpora.is_empty() {
                "Corpus".to_string()
            } else {
                format!("Corpus: {}", self.state.corpus_name())
            };
            ui.menu_button(corpus_label, |ui| {
                let mut switch_to = None;
                for (i, corpus) in self.state.corpora.iter().enumerate() {
                    if ui
                        .selectable_label(i == self.state.active_corpus_idx, &corpus.name)
                        .clicked()
                    {
                        switch_to = Some(i);
                        ui.close();
                    }
                }
                if let Some(idx) = switch_to {
                    self.switch_corpus(idx);
                }
            });
        });
    }
}

impl eframe::App for AtheneumApp {
    fn logic(&mut self, ctx: &egui::Context, _frame: &mut eframe::Frame) {
        let mut pending = self.pending.lock().unwrap();

        // Corpora list
        if let Some(result) = pending.corpora.take() {
            match result {
                Ok(corpora) => {
                    tracing::info!(count = corpora.len(), "loaded corpora list");
                    self.state.corpora = corpora;
                    self.load_state = LoadState::Ready;
                    drop(pending);
                    self.fetch_facets();
                    self.fetch_records();
                    pending = self.pending.lock().unwrap();
                }
                Err(e) => {
                    tracing::error!(%e, "failed to fetch corpora");
                    self.state.load_error = Some(e.clone());
                    self.load_state = LoadState::Error;
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

        // Detail responses — insert into open_windows
        let completed = std::mem::take(&mut pending.details);
        drop(pending);

        for (uuid, result) in completed {
            self.details_in_flight.remove(&uuid);
            match result {
                Ok(Some(detail)) => {
                    self.state.open_windows.insert(uuid, detail);
                }
                Ok(None) => tracing::warn!(%uuid, "record not found"),
                Err(e) => tracing::warn!(%uuid, %e, "failed to fetch record detail"),
            }
        }

        if matches!(self.load_state, LoadState::Loading) {
            ctx.request_repaint();
        }
    }

    fn ui(&mut self, ui: &mut egui::Ui, _frame: &mut eframe::Frame) {
        // Loading screen
        if matches!(self.load_state, LoadState::Loading) {
            egui::CentralPanel::default().show_inside(ui, |ui| {
                ui.centered_and_justified(|ui| {
                    ui.heading("Loading corpora...");
                });
            });
            return;
        }

        // Menu bar
        egui::Panel::top("menu_bar").show_inside(ui, |ui| {
            self.menu_bar(ui);
        });

        // Filter bar
        if self.state.show_filter_bar {
            egui::Panel::top("filter_bar").show_inside(ui, |ui| {
                let action = views::filter_bar(ui, &mut self.state);
                match action {
                    views::FilterAction::None => {}
                    views::FilterAction::RefreshRecords => {
                        self.fetch_records();
                    }
                }
            });
        }

        // Status bar
        egui::Panel::bottom("status_bar").show_inside(ui, |ui| {
            views::status_bar(ui, &self.state);
        });

        // Sidebar
        if self.state.show_sidebar {
            egui::Panel::left("sidebar")
                .default_size(320.0)
                .resizable(true)
                .show_inside(ui, |ui| {
                    if let Some(uuid) = views::sidebar(ui, &mut self.state) {
                        if !self.state.open_windows.contains_key(&uuid) {
                            self.fetch_detail(uuid);
                        }
                    }
                });
        }

        // Central panel: landing when no windows open
        egui::CentralPanel::default().show_inside(ui, |ui| {
            if self.state.open_windows.is_empty() {
                ui.centered_and_justified(|ui| {
                    ui.heading("Click a record to open it");
                });
            }
        });

        // Detail windows
        let ctx = ui.ctx().clone();
        let mut to_close = Vec::new();
        let mut nav_requests = Vec::new();

        let window_entries: Vec<(Uuid, RecordDetail)> = self
            .state
            .open_windows
            .iter()
            .map(|(k, v)| (*k, v.clone()))
            .collect();

        for (uuid, detail) in &window_entries {
            let title = &detail.record.frontmatter.title;
            let mut is_open = true;

            egui::Window::new(title)
                .id(egui::Id::new(uuid))
                .open(&mut is_open)
                .default_size([600.0, 500.0])
                .resizable(true)
                .show(&ctx, |ui| {
                    let navs = views::detail_content(ui, detail);
                    nav_requests.extend(navs);
                });

            if !is_open {
                to_close.push(*uuid);
            }
        }

        for uuid in to_close {
            self.state.open_windows.remove(&uuid);
        }

        for uuid in nav_requests {
            if !self.state.open_windows.contains_key(&uuid) {
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
