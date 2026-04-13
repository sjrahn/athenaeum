use crate::state::AppState;

/// Renders the corpora list. Returns Some(idx) if a corpus was clicked.
pub fn corpora_window(ui: &mut egui::Ui, state: &AppState) -> Option<usize> {
    let mut switch_to = None;

    for (i, corpus) in state.corpora.iter().enumerate() {
        let selected = i == state.active_corpus_idx;
        let label = format!("{} ({} records)", corpus.name, corpus.record_count);
        if ui.selectable_label(selected, label).clicked() && !selected {
            switch_to = Some(i);
        }
    }

    switch_to
}
