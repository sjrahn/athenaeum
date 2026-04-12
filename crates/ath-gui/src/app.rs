use std::collections::BTreeMap;
use std::sync::{Arc, Mutex};

use ath_core::api_types::{
    CorpusInfo, FacetsResponse, QueryResult, RecordDetail, SubmissionsResponse, SubmitResponse,
};
use uuid::Uuid;

use crate::state::{AppState, PendingFile};
use crate::views;

/// Pending HTTP responses, polled each frame.
#[derive(Default)]
struct PendingRequests {
    corpora: Option<Result<Vec<CorpusInfo>, String>>,
    facets: Option<Result<FacetsResponse, String>>,
    records: Option<Result<QueryResult, String>>,
    /// Detail responses keyed by UUID (supports multiple in-flight window fetches).
    details: BTreeMap<Uuid, Result<Option<RecordDetail>, String>>,
    submit_result: Option<Result<SubmitResponse, String>>,
    submissions_list: Option<Result<SubmissionsResponse, String>>,
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
        self.state.submissions.clear();
        self.fetch_facets();
        self.fetch_records();
        if self.state.show_submit_panel {
            self.fetch_submissions();
        }
    }

    pub fn submit_capture(&mut self) {
        if self.state.corpora.is_empty() {
            return;
        }

        let corpus = self.state.corpus_name().to_owned();
        let title = self.state.submit_title.clone();
        let url = self.state.submit_url.clone();
        let description = self.state.submit_description.clone();
        let source_type = self.state.submit_source_type.clone();
        let files = std::mem::take(&mut self.state.submit_files);
        let server_url = self.server_url.clone();
        let pending = self.pending.clone();

        self.state.submit_status = Some("Submitting...".to_string());

        // Build multipart body
        let mut builder = ehttp::multipart::MultipartBuilder::new()
            .add_text("corpus", &corpus);

        if !title.is_empty() {
            builder = builder.add_text("title", &title);
        }
        if !url.is_empty() {
            builder = builder.add_text("url", &url);
        }
        if !description.is_empty() {
            builder = builder.add_text("description", &description);
        }
        if !source_type.is_empty() {
            builder = builder.add_text("source_type", &source_type);
        }

        for file in &files {
            if let Some(bytes) = &file.bytes {
                let mut cursor = std::io::Cursor::new(bytes.as_ref());
                match builder.add_stream(&mut cursor, "file", Some(&file.name), None) {
                    Ok(b) => builder = b,
                    Err(e) => {
                        tracing::error!(%e, name = %file.name, "failed to add file to multipart");
                        self.state.submit_status = Some(format!("Error: {e}"));
                        self.state.submit_files = files;
                        return;
                    }
                }
            } else {
                #[cfg(not(target_arch = "wasm32"))]
                if let Some(path) = &file.path {
                    match builder.add_file("file", path) {
                        Ok(b) => builder = b,
                        Err(e) => {
                            tracing::error!(%e, path = %path.display(), "failed to add file to multipart");
                            self.state.submit_status = Some(format!("Error: {e}"));
                            self.state.submit_files = files;
                            return;
                        }
                    }
                }
            }
        }

        let api_url = format!("{}/api/submit", server_url);
        let request = ehttp::Request::post_multipart(api_url, builder);

        ehttp::fetch(request, move |result| {
            let outcome = parse_response::<SubmitResponse>(result);
            pending.lock().unwrap().submit_result = Some(outcome);
        });
    }

    pub fn fetch_submissions(&mut self) {
        if self.state.corpora.is_empty() {
            return;
        }
        let corpus = self.state.corpus_name().to_owned();
        let url = format!(
            "{}/api/submissions?corpus={}",
            self.server_url,
            url_encode(&corpus)
        );
        let pending = self.pending.clone();

        ehttp::fetch(ehttp::Request::get(&url), move |result| {
            let outcome = parse_response::<SubmissionsResponse>(result);
            pending.lock().unwrap().submissions_list = Some(outcome);
        });
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
                if ui
                    .checkbox(&mut self.state.show_submit_panel, "Submit Panel")
                    .changed()
                    && self.state.show_submit_panel
                {
                    self.fetch_submissions();
                }
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

        // Submit result
        let mut refresh_submissions = false;
        if let Some(result) = pending.submit_result.take() {
            match result {
                Ok(resp) => {
                    self.state.submit_status =
                        Some(format!("Staged: {} ({} files)", resp.folder, resp.file_count));
                    self.state.submit_title.clear();
                    self.state.submit_url.clear();
                    self.state.submit_description.clear();
                    self.state.submit_source_type.clear();
                    self.state.submit_files.clear();
                    refresh_submissions = true;
                }
                Err(e) => {
                    tracing::warn!(%e, "submission failed");
                    self.state.submit_status = Some(format!("Error: {e}"));
                }
            }
        }

        // Submissions list
        if let Some(result) = pending.submissions_list.take() {
            match result {
                Ok(resp) => self.state.submissions = resp.submissions,
                Err(e) => tracing::warn!(%e, "failed to fetch submissions"),
            }
        }

        // Detail responses — insert into open_windows
        let completed = std::mem::take(&mut pending.details);
        drop(pending);

        if refresh_submissions {
            self.fetch_submissions();
        }

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

        // Submit panel (bottom, before status bar)
        if self.state.show_submit_panel {
            egui::Panel::bottom("submit_panel")
                .default_size(200.0)
                .resizable(true)
                .show_inside(ui, |ui| {
                    let action = views::submit_panel(ui, &mut self.state);
                    match action {
                        views::SubmitAction::None => {}
                        views::SubmitAction::Submit => {
                            self.submit_capture();
                            // Refresh queue after a short delay (submit is async)
                        }
                        views::SubmitAction::RemoveFile(idx) => {
                            self.state.submit_files.remove(idx);
                        }
                        views::SubmitAction::RefreshQueue => {
                            self.fetch_submissions();
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

        // Handle drag-drop: accumulate files into submit builder
        if self.state.show_submit_panel {
            let dropped: Vec<egui::DroppedFile> =
                ui.ctx().input(|i| i.raw.dropped_files.clone());
            for file in dropped {
                let name = file
                    .name
                    .clone();
                let name = if name.is_empty() {
                    file.path
                        .as_ref()
                        .and_then(|p| p.file_name())
                        .map(|n| n.to_string_lossy().to_string())
                        .unwrap_or_else(|| "unnamed".to_string())
                } else {
                    name
                };
                self.state.submit_files.push(PendingFile {
                    name,
                    path: file.path.clone(),
                    bytes: file.bytes.clone(),
                });
            }
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
