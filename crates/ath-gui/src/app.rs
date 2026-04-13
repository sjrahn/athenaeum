use std::collections::BTreeMap;
use std::sync::{Arc, Mutex};

use ath_core::api_types::{
    CorpusInfo, FacetsResponse, QueryResult, RecordDetail, SubmissionsResponse, SubmitResponse,
};
use uuid::Uuid;

use crate::state::{AppState, PendingFile, PreviewContent, PreviewState};
use crate::views;

/// Pending HTTP responses, polled each frame.
#[derive(Default)]
struct PendingRequests {
    corpora: Option<Result<Vec<CorpusInfo>, String>>,
    facets: Option<Result<FacetsResponse, String>>,
    records: Option<Result<QueryResult, String>>,
    details: BTreeMap<Uuid, Result<Option<RecordDetail>, String>>,
    submit_result: Option<Result<SubmitResponse, String>>,
    submissions_list: Option<Result<SubmissionsResponse, String>>,
    /// Preview file responses: key -> (bytes, content_type_header)
    previews: BTreeMap<String, Result<(Vec<u8>, String), String>>,
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
        if self.state.show_submit_window {
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

        let mut builder =
            ehttp::multipart::MultipartBuilder::new().add_text("corpus", &corpus);

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

    pub fn fetch_preview(&mut self, req: &views::ArtifactRequest) {
        let key = format!("{}/{}/{}/{}", req.corpus, req.kind, req.uuid, req.filename);

        // Don't re-fetch if already open or loading
        if self.state.open_previews.contains_key(&key) {
            return;
        }

        // Insert loading placeholder
        self.state.open_previews.insert(
            key.clone(),
            PreviewState {
                title: req.filename.clone(),
                content: PreviewContent::Loading,
            },
        );

        let url = format!(
            "{}/api/files/{}/{}/{}/{}",
            self.server_url, req.corpus, req.kind, req.uuid, req.filename
        );
        let pending = self.pending.clone();
        let fetch_key = key.clone();
        ehttp::fetch(ehttp::Request::get(&url), move |result| {
            let outcome = match result {
                Ok(response) if response.ok => {
                    let ct = response
                        .headers
                        .get("content-type")
                        .map(|s| s.to_string())
                        .unwrap_or_else(|| "application/octet-stream".to_string());
                    Ok((response.bytes, ct))
                }
                Ok(response) => Err(format!(
                    "Server error: {} {}",
                    response.status, response.status_text
                )),
                Err(e) => Err(e),
            };
            pending.lock().unwrap().previews.insert(fetch_key, outcome);
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
                if ui
                    .checkbox(&mut self.state.show_corpora_window, "Corpora")
                    .changed()
                {}
                if ui
                    .checkbox(&mut self.state.show_records_window, "Records")
                    .changed()
                {}
                if ui
                    .checkbox(&mut self.state.show_submit_window, "Submit")
                    .changed()
                    && self.state.show_submit_window
                {
                    self.fetch_submissions();
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

        // Preview responses
        let completed_previews = std::mem::take(&mut pending.previews);
        for (key, result) in completed_previews {
            let content = match result {
                Ok((bytes, content_type)) => classify_preview(bytes, &content_type, &key),
                Err(e) => PreviewContent::Error(e),
            };
            if let Some(preview) = self.state.open_previews.get_mut(&key) {
                preview.content = content;
            }
        }

        // Detail responses
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

        // Status bar
        let mut open_corpora = false;
        egui::Panel::bottom("status_bar").show_inside(ui, |ui| {
            ui.horizontal(|ui| {
                // Corpus selector — clicking opens the Corpora window
                let corpus_label = if self.state.corpora.is_empty() {
                    "No corpus".to_string()
                } else {
                    self.state.corpus_name().to_string()
                };
                if ui.small_button(&corpus_label).clicked() {
                    open_corpora = true;
                }

                ui.separator();

                // Record count
                let total = self.state.sidebar_total;
                let showing = self.state.sidebar_entries.len();
                if showing as u64 == total {
                    ui.weak(format!("{total} records"));
                } else {
                    ui.weak(format!("{showing} / {total} records"));
                }

                // Open windows count
                if !self.state.open_windows.is_empty() {
                    ui.separator();
                    ui.weak(format!("{} open", self.state.open_windows.len()));
                }
            });
        });
        if open_corpora {
            self.state.show_corpora_window = true;
        }

        // Background
        egui::CentralPanel::default().show_inside(ui, |_| {});

        let ctx = ui.ctx().clone();

        // Corpora window
        if self.state.show_corpora_window {
            let mut open = true;
            egui::Window::new("Corpora")
                .id(egui::Id::new("corpora_window"))
                .open(&mut open)
                .default_size([250.0, 200.0])
                .resizable(true)
                .show(&ctx, |ui| {
                    if let Some(idx) = views::corpora_window(ui, &self.state) {
                        self.switch_corpus(idx);
                    }
                });
            if !open {
                self.state.show_corpora_window = false;
            }
        }

        // Records window
        if self.state.show_records_window {
            let mut open = true;
            let title = format!(
                "Records \u{2014} {} ({})",
                self.state.corpus_name(),
                self.state.sidebar_total
            );
            egui::Window::new(title)
                .id(egui::Id::new("records_window"))
                .open(&mut open)
                .default_size([500.0, 600.0])
                .resizable(true)
                .show(&ctx, |ui| {
                    let action = views::records_window(ui, &mut self.state);
                    match action {
                        views::RecordsAction::None => {}
                        views::RecordsAction::RefreshRecords => {
                            self.fetch_records();
                        }
                        views::RecordsAction::OpenDetail(uuid) => {
                            if !self.state.open_windows.contains_key(&uuid) {
                                self.fetch_detail(uuid);
                            }
                        }
                    }
                });
            if !open {
                self.state.show_records_window = false;
            }
        }

        // Submit window
        if self.state.show_submit_window {
            let mut open = true;
            egui::Window::new("Submit")
                .id(egui::Id::new("submit_window"))
                .open(&mut open)
                .default_size([600.0, 300.0])
                .resizable(true)
                .show(&ctx, |ui| {
                    let action = views::submit_panel(ui, &mut self.state);
                    match action {
                        views::SubmitAction::None => {}
                        views::SubmitAction::Submit => {
                            self.submit_capture();
                        }
                        views::SubmitAction::RemoveFile(idx) => {
                            self.state.submit_files.remove(idx);
                        }
                        views::SubmitAction::RefreshQueue => {
                            self.fetch_submissions();
                        }
                    }
                });
            if !open {
                self.state.show_submit_window = false;
            }
        }

        // Drag-drop: accumulate files into submit builder when submit window is open
        if self.state.show_submit_window {
            let dropped: Vec<egui::DroppedFile> =
                ctx.input(|i| i.raw.dropped_files.clone());
            for file in dropped {
                let name = file.name.clone();
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

        // Detail windows
        let mut to_close = Vec::new();
        let mut nav_requests = Vec::new();
        let mut artifact_requests = Vec::new();
        let corpus_name = self.state.corpus_name().to_string();

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
                    let actions = views::detail_content(ui, detail, &corpus_name);
                    nav_requests.extend(actions.nav_requests);
                    artifact_requests.extend(actions.artifact_requests);
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

        for req in &artifact_requests {
            self.fetch_preview(req);
        }

        // Preview windows
        let preview_keys: Vec<String> = self.state.open_previews.keys().cloned().collect();
        let mut previews_to_close = Vec::new();

        for key in &preview_keys {
            let preview = &self.state.open_previews[key];
            let title = &preview.title;
            let mut is_open = true;

            egui::Window::new(title)
                .id(egui::Id::new(format!("preview_{key}")))
                .open(&mut is_open)
                .default_size([500.0, 400.0])
                .resizable(true)
                .show(&ctx, |ui| {
                    match &preview.content {
                        PreviewContent::Loading => {
                            ui.centered_and_justified(|ui| {
                                ui.spinner();
                            });
                        }
                        PreviewContent::Image { uri, bytes } => {
                            egui::ScrollArea::both()
                                .auto_shrink([false; 2])
                                .show(ui, |ui| {
                                    let image = egui::Image::from_bytes(uri.clone(), bytes.clone());
                                    ui.add(image);
                                });
                        }
                        PreviewContent::Text(text) => {
                            egui::ScrollArea::both()
                                .auto_shrink([false; 2])
                                .show(ui, |ui| {
                                    ui.monospace(text);
                                });
                        }
                        PreviewContent::Unsupported { filename, size } => {
                            ui.vertical_centered(|ui| {
                                ui.add_space(20.0);
                                ui.heading(filename);
                                ui.label(format!("{} bytes", size));
                                ui.add_space(8.0);
                                ui.weak("Preview not available for this file type");
                            });
                        }
                        PreviewContent::Error(e) => {
                            ui.colored_label(egui::Color32::RED, format!("Error: {e}"));
                        }
                    }
                });

            if !is_open {
                previews_to_close.push(key.clone());
            }
        }

        for key in previews_to_close {
            self.state.open_previews.remove(&key);
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

/// Classify fetched bytes into a preview content type.
fn classify_preview(bytes: Vec<u8>, content_type: &str, key: &str) -> PreviewContent {
    if content_type.starts_with("image/") {
        let uri = format!("bytes://{key}");
        let arc_bytes: Arc<[u8]> = bytes.into();
        PreviewContent::Image {
            uri,
            bytes: arc_bytes,
        }
    } else if content_type.starts_with("text/")
        || content_type == "application/json"
        || content_type == "application/xml"
        || content_type == "application/javascript"
    {
        match String::from_utf8(bytes) {
            Ok(text) => PreviewContent::Text(text),
            Err(e) => PreviewContent::Error(format!("Not valid UTF-8: {e}")),
        }
    } else {
        let size = bytes.len();
        let filename = key.rsplit('/').next().unwrap_or(key).to_string();
        PreviewContent::Unsupported { filename, size }
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
