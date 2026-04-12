use crate::state::{AppState, SortOrder};

/// Action returned by the filter bar for the app to handle.
pub enum FilterAction {
    None,
    SwitchCorpus(usize),
    RefreshRecords,
}

pub fn filter_bar(ui: &mut egui::Ui, state: &mut AppState) -> FilterAction {
    let mut action = FilterAction::None;

    ui.add_space(4.0);

    // Row 1: Corpus switcher, search, sort
    ui.horizontal(|ui| {
        // Corpus switcher
        if state.corpora.len() > 1 {
            ui.label("Corpus:");
            let current_name = state.corpus_name().to_owned();
            let corpus_names: Vec<(usize, String)> = state
                .corpora
                .iter()
                .enumerate()
                .map(|(i, c)| (i, c.name.clone()))
                .collect();
            let mut switch_to = None;
            egui::ComboBox::from_id_salt("corpus_switcher")
                .selected_text(&current_name)
                .show_ui(ui, |ui| {
                    for (i, name) in &corpus_names {
                        if ui
                            .selectable_label(*i == state.active_corpus_idx, name)
                            .clicked()
                        {
                            switch_to = Some(*i);
                        }
                    }
                });
            if let Some(idx) = switch_to {
                action = FilterAction::SwitchCorpus(idx);
            }

            ui.separator();
        }

        // Search input
        ui.label("Search:");
        let search_response = ui.add(
            egui::TextEdit::singleline(&mut state.search_text).desired_width(200.0),
        );
        if search_response.lost_focus() && ui.input(|i| i.key_pressed(egui::Key::Enter)) {
            action = FilterAction::RefreshRecords;
        }

        ui.separator();

        // Sort order
        ui.label("Sort:");
        let sort_label = match state.sort_order {
            SortOrder::TitleAsc => "Title A-Z",
            SortOrder::TitleDesc => "Title Z-A",
            SortOrder::StatusAsc => "Status",
            SortOrder::NewestFirst => "Newest",
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
                changed |= ui
                    .selectable_value(&mut state.sort_order, SortOrder::NewestFirst, "Newest")
                    .changed();
                if changed {
                    action = FilterAction::RefreshRecords;
                }
            });
    });

    ui.add_space(2.0);

    // Row 2: Source / Document tabs + type-specific filters
    ui.horizontal(|ui| {
        // Tab-style type selector: All | Sources | Documents
        let current_type = state.filter_record_type.clone();

        if ui
            .selectable_label(current_type.is_none(), "All")
            .clicked()
            && current_type.is_some()
        {
            state.filter_record_type = None;
            // Clear type-specific filters when switching
            state.filter_origin_name = None;
            state.filter_credibility_tier = None;
            action = FilterAction::RefreshRecords;
        }

        if ui
            .selectable_label(current_type.as_deref() == Some("source"), "Sources")
            .clicked()
            && current_type.as_deref() != Some("source")
        {
            state.filter_record_type = Some("source".to_string());
            action = FilterAction::RefreshRecords;
        }

        if ui
            .selectable_label(current_type.as_deref() == Some("document"), "Documents")
            .clicked()
            && current_type.as_deref() != Some("document")
        {
            state.filter_record_type = Some("document".to_string());
            // Clear source-specific filters
            state.filter_origin_name = None;
            state.filter_credibility_tier = None;
            action = FilterAction::RefreshRecords;
        }

        ui.separator();

        let facets = state.facets.clone();

        // Shared filters: Content Type, Status, Tag
        if let Some(ref facets) = facets {
            let options: Vec<&str> = facets.content_types.iter().map(|s| s.as_str()).collect();
            if filter_combo(
                ui,
                "filter_content_type",
                "Content Type",
                &mut state.filter_content_type,
                &options,
            ) {
                action = FilterAction::RefreshRecords;
            }
        }

        if let Some(ref facets) = facets {
            let options: Vec<&str> = facets.statuses.iter().map(|s| s.as_str()).collect();
            if filter_combo(
                ui,
                "filter_status",
                "Status",
                &mut state.filter_status,
                &options,
            ) {
                action = FilterAction::RefreshRecords;
            }
        }

        if let Some(ref facets) = facets {
            if !facets.tags.is_empty() {
                let options: Vec<&str> = facets.tags.iter().map(|s| s.as_str()).collect();
                if filter_combo(
                    ui,
                    "filter_tag",
                    "Tag",
                    &mut state.filter_tag,
                    &options,
                ) {
                    action = FilterAction::RefreshRecords;
                }
            }
        }

        // Source-specific filters (only shown when viewing sources or all)
        if current_type.is_none() || current_type.as_deref() == Some("source") {
            if let Some(ref facets) = facets {
                if !facets.origin_names.is_empty() {
                    let options: Vec<&str> =
                        facets.origin_names.iter().map(|s| s.as_str()).collect();
                    if filter_combo(
                        ui,
                        "filter_origin",
                        "Origin",
                        &mut state.filter_origin_name,
                        &options,
                    ) {
                        action = FilterAction::RefreshRecords;
                    }
                }
            }

            if let Some(ref facets) = facets {
                if !facets.credibility_tiers.is_empty() {
                    let options: Vec<&str> =
                        facets.credibility_tiers.iter().map(|s| s.as_str()).collect();
                    if filter_combo(
                        ui,
                        "filter_credibility",
                        "Credibility",
                        &mut state.filter_credibility_tier,
                        &options,
                    ) {
                        action = FilterAction::RefreshRecords;
                    }
                }
            }
        }

        ui.separator();

        // Clear all filters
        let has_filters = !state.search_text.is_empty()
            || state.filter_content_type.is_some()
            || state.filter_status.is_some()
            || state.filter_tag.is_some()
            || state.filter_origin_name.is_some()
            || state.filter_credibility_tier.is_some()
            || state.filter_record_type.is_some();

        if has_filters && ui.button("Clear all").clicked() {
            state.search_text.clear();
            state.filter_content_type = None;
            state.filter_status = None;
            state.filter_tag = None;
            state.filter_origin_name = None;
            state.filter_credibility_tier = None;
            state.filter_record_type = None;
            action = FilterAction::RefreshRecords;
        }
    });

    ui.add_space(4.0);

    action
}

/// Render a filter combo box. Returns true if the value changed.
fn filter_combo(
    ui: &mut egui::Ui,
    id: &str,
    label: &str,
    value: &mut Option<String>,
    options: &[&str],
) -> bool {
    let display = value.as_deref().unwrap_or("All");
    let mut changed = false;

    egui::ComboBox::from_id_salt(id)
        .selected_text(format!("{label}: {display}"))
        .width(160.0)
        .show_ui(ui, |ui| {
            if ui.selectable_label(value.is_none(), "All").clicked() {
                *value = None;
                changed = true;
            }

            ui.separator();

            for option in options {
                let selected = value.as_deref() == Some(option);
                if ui.selectable_label(selected, *option).clicked() {
                    *value = Some(option.to_string());
                    changed = true;
                }
            }
        });

    changed
}

pub fn status_bar(ui: &mut egui::Ui, state: &AppState) {
    ui.horizontal(|ui| {
        let total = state.sidebar_total;
        let showing = state.sidebar_entries.len();

        if showing as u64 == total {
            ui.label(format!("{total} records"));
        } else {
            ui.label(format!("{showing} / {total} records"));
        }

        ui.separator();
        ui.weak(state.corpus_name());
    });
}
