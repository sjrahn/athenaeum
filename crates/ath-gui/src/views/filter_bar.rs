use crate::state::{AppState, SortOrder};

pub fn filter_bar(ui: &mut egui::Ui, state: &mut AppState) {
    ui.horizontal(|ui| {
        // Search input
        ui.label("Search:");
        let search_response = ui.text_edit_singleline(&mut state.filter.search_text);
        if search_response.changed() {
            state.recompute_filtered_list();
        }

        ui.separator();

        // Sort order
        ui.label("Sort:");
        let sort_label = match state.sort_order {
            SortOrder::TitleAsc => "Title A-Z",
            SortOrder::TitleDesc => "Title Z-A",
            SortOrder::StatusAsc => "Status",
        };
        egui::ComboBox::from_id_salt("sort_order")
            .selected_text(sort_label)
            .show_ui(ui, |ui| {
                let mut changed = false;
                changed |= ui
                    .selectable_value(&mut state.sort_order, SortOrder::TitleAsc, "Title A-Z")
                    .changed();
                changed |= ui
                    .selectable_value(&mut state.sort_order, SortOrder::TitleDesc, "Title Z-A")
                    .changed();
                changed |= ui
                    .selectable_value(&mut state.sort_order, SortOrder::StatusAsc, "Status")
                    .changed();
                if changed {
                    state.recompute_filtered_list();
                }
            });

        // Clear filters button
        if !state.filter.is_empty() {
            if ui.button("Clear filters").clicked() {
                state.filter = Default::default();
                state.recompute_filtered_list();
            }
        }
    });
}

pub fn status_bar(ui: &mut egui::Ui, state: &AppState) {
    ui.horizontal(|ui| {
        let total = state.corpus.len();
        let filtered = state.filtered_uuids.len();

        if filtered == total {
            ui.label(format!("{total} records"));
        } else {
            ui.label(format!("{filtered} / {total} records"));
        }

        ui.separator();
        ui.weak(format!("corpus: {}", state.corpus.root_path.display()));
    });
}
