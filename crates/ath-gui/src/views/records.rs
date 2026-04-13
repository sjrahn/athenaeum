use uuid::Uuid;

use crate::state::{AppState, SortOrder};

/// Height of each row in the record list.
const ROW_HEIGHT: f32 = 56.0;

/// Action returned by the records window.
pub enum RecordsAction {
    None,
    RefreshRecords,
    OpenDetail(Uuid),
}

/// Renders the records window content: filters + record list.
pub fn records_window(ui: &mut egui::Ui, state: &mut AppState) -> RecordsAction {
    let mut action = RecordsAction::None;

    // -- Filters section --

    // Row 1: Search + sort
    ui.horizontal(|ui| {
        ui.label("Search:");
        let search_response = ui.add(
            egui::TextEdit::singleline(&mut state.search_text).desired_width(200.0),
        );
        if search_response.lost_focus() && ui.input(|i| i.key_pressed(egui::Key::Enter)) {
            action = RecordsAction::RefreshRecords;
        }

        ui.separator();

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
                    action = RecordsAction::RefreshRecords;
                }
            });
    });

    // Row 2: Type tabs + filter combos (wrapping)
    ui.horizontal_wrapped(|ui| {
        let current_type = state.filter_record_type.clone();

        if ui
            .selectable_label(current_type.is_none(), "All")
            .clicked()
            && current_type.is_some()
        {
            state.filter_record_type = None;
            state.filter_origin_name = None;
            state.filter_credibility_tier = None;
            action = RecordsAction::RefreshRecords;
        }

        if ui
            .selectable_label(current_type.as_deref() == Some("source"), "Sources")
            .clicked()
            && current_type.as_deref() != Some("source")
        {
            state.filter_record_type = Some("source".to_string());
            action = RecordsAction::RefreshRecords;
        }

        if ui
            .selectable_label(current_type.as_deref() == Some("document"), "Documents")
            .clicked()
            && current_type.as_deref() != Some("document")
        {
            state.filter_record_type = Some("document".to_string());
            state.filter_origin_name = None;
            state.filter_credibility_tier = None;
            action = RecordsAction::RefreshRecords;
        }

        ui.separator();

        let facets = state.facets.clone();

        if let Some(ref facets) = facets {
            let options: Vec<&str> = facets.content_types.iter().map(|s| s.as_str()).collect();
            if filter_combo(ui, "filter_content_type", "Content Type", &mut state.filter_content_type, &options) {
                action = RecordsAction::RefreshRecords;
            }
        }

        if let Some(ref facets) = facets {
            let options: Vec<&str> = facets.statuses.iter().map(|s| s.as_str()).collect();
            if filter_combo(ui, "filter_status", "Status", &mut state.filter_status, &options) {
                action = RecordsAction::RefreshRecords;
            }
        }

        if let Some(ref facets) = facets {
            if !facets.tags.is_empty() {
                let options: Vec<&str> = facets.tags.iter().map(|s| s.as_str()).collect();
                if filter_combo(ui, "filter_tag", "Tag", &mut state.filter_tag, &options) {
                    action = RecordsAction::RefreshRecords;
                }
            }
        }

        if current_type.is_none() || current_type.as_deref() == Some("source") {
            if let Some(ref facets) = facets {
                if !facets.origin_names.is_empty() {
                    let options: Vec<&str> = facets.origin_names.iter().map(|s| s.as_str()).collect();
                    if filter_combo(ui, "filter_origin", "Origin", &mut state.filter_origin_name, &options) {
                        action = RecordsAction::RefreshRecords;
                    }
                }
            }

            if let Some(ref facets) = facets {
                if !facets.credibility_tiers.is_empty() {
                    let options: Vec<&str> = facets.credibility_tiers.iter().map(|s| s.as_str()).collect();
                    if filter_combo(ui, "filter_credibility", "Credibility", &mut state.filter_credibility_tier, &options) {
                        action = RecordsAction::RefreshRecords;
                    }
                }
            }
        }

        ui.separator();

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
            action = RecordsAction::RefreshRecords;
        }
    });

    ui.separator();

    // -- Record list section --

    if let Some(ref err) = state.load_error {
        ui.colored_label(egui::Color32::RED, format!("Load error: {err}"));
        return action;
    }

    if state.corpora.is_empty() {
        ui.label("No corpus loaded.");
        return action;
    }

    if state.sidebar_entries.is_empty() {
        ui.label("No records found.");
        return action;
    }

    let total_rows = state.sidebar_entries.len();

    egui::ScrollArea::vertical()
        .auto_shrink([false; 2])
        .show_rows(ui, ROW_HEIGHT, total_rows, |ui, row_range| {
            for row_idx in row_range {
                let entry = &state.sidebar_entries[row_idx];
                let is_open = state.open_windows.contains_key(&entry.uuid);

                let response = ui.push_id(entry.uuid, |ui| {
                    let frame = if is_open {
                        egui::Frame::NONE
                            .inner_margin(6.0)
                            .corner_radius(4.0)
                            .fill(ui.visuals().selection.bg_fill)
                    } else {
                        egui::Frame::NONE.inner_margin(6.0).corner_radius(4.0)
                    };

                    frame.show(ui, |ui| {
                        ui.set_width(ui.available_width());

                        ui.horizontal(|ui| {
                            let status_color = match entry.status.as_str() {
                                "stub" => egui::Color32::from_rgb(220, 50, 50),
                                "draft" => egui::Color32::from_rgb(220, 180, 50),
                                "normalized" => egui::Color32::from_rgb(50, 180, 50),
                                _ => egui::Color32::GRAY,
                            };
                            let (rect, _) =
                                ui.allocate_exact_size(egui::vec2(8.0, 8.0), egui::Sense::hover());
                            ui.painter()
                                .circle_filled(rect.center(), 4.0, status_color);

                            let title_text = if entry.title.chars().count() > 50 {
                                let truncated: String = entry.title.chars().take(47).collect();
                                format!("{truncated}...")
                            } else {
                                entry.title.clone()
                            };
                            ui.strong(title_text);
                        });

                        ui.horizontal(|ui| {
                            let type_color = match entry.record_type.as_str() {
                                "source" => egui::Color32::from_rgb(70, 130, 200),
                                "document" => egui::Color32::from_rgb(70, 180, 100),
                                _ => egui::Color32::GRAY,
                            };
                            ui.colored_label(type_color, &entry.content_type);

                            for (i, tag) in entry.tags.iter().enumerate() {
                                if i >= 3 {
                                    let remaining = entry.tags.len() - 3;
                                    ui.weak(format!("+{remaining}"));
                                    break;
                                }
                                ui.weak(format!("#{tag}"));
                            }
                        });
                    })
                });

                if response.inner.response.interact(egui::Sense::click()).clicked() {
                    action = RecordsAction::OpenDetail(entry.uuid);
                }
            }
        });

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
