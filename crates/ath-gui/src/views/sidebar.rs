use uuid::Uuid;

use crate::state::AppState;

/// Height of each row in the sidebar.
const ROW_HEIGHT: f32 = 56.0;

/// Renders the sidebar. Returns Some(uuid) if a record was clicked.
pub fn sidebar(ui: &mut egui::Ui, state: &mut AppState) -> Option<Uuid> {
    if let Some(ref err) = state.load_error {
        ui.colored_label(egui::Color32::RED, format!("Load error: {err}"));
        return None;
    }

    if state.corpora.is_empty() {
        ui.centered_and_justified(|ui| {
            ui.label("No corpus loaded.");
        });
        return None;
    }

    if state.sidebar_entries.is_empty() {
        ui.centered_and_justified(|ui| {
            ui.label("No records found.");
        });
        return None;
    }

    ui.heading(format!("{} records", state.sidebar_total));
    ui.separator();

    let total_rows = state.sidebar_entries.len();
    let mut clicked_uuid = None;

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

                        // Title row
                        ui.horizontal(|ui| {
                            // Status dot
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

                            // Title
                            let title_text = if entry.title.chars().count() > 50 {
                                let truncated: String = entry.title.chars().take(47).collect();
                                format!("{truncated}...")
                            } else {
                                entry.title.clone()
                            };
                            ui.strong(title_text);
                        });

                        // Type badge row
                        ui.horizontal(|ui| {
                            let type_color = match entry.record_type.as_str() {
                                "source" => egui::Color32::from_rgb(70, 130, 200),
                                "document" => egui::Color32::from_rgb(70, 180, 100),
                                _ => egui::Color32::GRAY,
                            };
                            ui.colored_label(type_color, &entry.content_type);

                            // Show first few tags
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

                // Handle click
                if response.inner.response.interact(egui::Sense::click()).clicked() {
                    clicked_uuid = Some(entry.uuid);
                }
            }
        });

    clicked_uuid
}
