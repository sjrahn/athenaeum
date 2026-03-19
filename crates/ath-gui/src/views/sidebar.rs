use ath_core::model::{RecordType, Status};
use uuid::Uuid;

use crate::state::AppState;

pub fn sidebar(ui: &mut egui::Ui, state: &mut AppState) {
    if let Some(ref err) = state.load_error {
        ui.colored_label(egui::Color32::RED, format!("Load error: {err}"));
        return;
    }

    if state.corpus.is_empty() {
        ui.centered_and_justified(|ui| {
            ui.label("No records found in corpus.");
        });
        return;
    }

    ui.heading(format!("{} records", state.filtered_uuids.len()));
    ui.separator();

    egui::ScrollArea::vertical()
        .auto_shrink([false; 2])
        .show(ui, |ui| {
            // Clone UUIDs to avoid borrowing state while iterating
            let uuids: Vec<Uuid> = state.filtered_uuids.clone();

            for uuid in &uuids {
                let Some(record) = state.corpus.get(uuid) else {
                    continue;
                };

                let fm = &record.frontmatter;
                let is_selected = state.selected_record == Some(*uuid);

                let response = ui.push_id(uuid, |ui| {
                    let frame = if is_selected {
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
                            let status_color = match fm.status {
                                Status::Stub => egui::Color32::from_rgb(220, 50, 50),
                                Status::Draft => egui::Color32::from_rgb(220, 180, 50),
                                Status::Normalized => egui::Color32::from_rgb(50, 180, 50),
                            };
                            let (rect, _) =
                                ui.allocate_exact_size(egui::vec2(8.0, 8.0), egui::Sense::hover());
                            ui.painter()
                                .circle_filled(rect.center(), 4.0, status_color);

                            // Title
                            let title_text = if fm.title.len() > 50 {
                                format!("{}...", &fm.title[..47])
                            } else {
                                fm.title.clone()
                            };
                            ui.strong(title_text);
                        });

                        // Type badge row
                        ui.horizontal(|ui| {
                            let type_color = match fm.record_type {
                                RecordType::Source => egui::Color32::from_rgb(70, 130, 200),
                                RecordType::Document => egui::Color32::from_rgb(70, 180, 100),
                            };
                            ui.colored_label(type_color, &fm.content_type);

                            // Show first few tags
                            for (i, tag) in fm.tags.iter().enumerate() {
                                if i >= 3 {
                                    let remaining = fm.tags.len() - 3;
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
                    state.selected_record = Some(*uuid);
                }

                ui.add_space(2.0);
            }
        });
}
