use std::path::PathBuf;

use ath_core::corpus::Corpus;

use crate::state::AppState;
use crate::views;

pub struct AtheneumApp {
    pub state: AppState,
}

impl AtheneumApp {
    pub fn new(corpus_path: PathBuf) -> Self {
        let state = match Corpus::load(&corpus_path) {
            Ok(corpus) => {
                tracing::info!(
                    path = %corpus_path.display(),
                    records = corpus.len(),
                    "corpus loaded"
                );
                AppState::new(corpus)
            }
            Err(e) => {
                tracing::error!(%e, "failed to load corpus");
                let mut state = AppState::new(Corpus {
                    records: Default::default(),
                    root_path: corpus_path,
                });
                state.load_error = Some(format!("{e}"));
                state
            }
        };

        AtheneumApp { state }
    }
}

impl eframe::App for AtheneumApp {
    fn update(&mut self, ctx: &egui::Context, _frame: &mut eframe::Frame) {
        // Top panel: filter bar
        egui::TopBottomPanel::top("filter_bar").show(ctx, |ui| {
            views::filter_bar(ui, &mut self.state);
        });

        // Bottom panel: status bar
        egui::TopBottomPanel::bottom("status_bar").show(ctx, |ui| {
            views::status_bar(ui, &self.state);
        });

        // Left panel: sidebar record list
        egui::SidePanel::left("sidebar")
            .default_width(320.0)
            .resizable(true)
            .show(ctx, |ui| {
                views::sidebar(ui, &mut self.state);
            });

        // Central panel: detail view
        egui::CentralPanel::default().show(ctx, |ui| {
            views::detail_view(ui, &mut self.state);
        });
    }
}
