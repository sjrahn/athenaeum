use egui_taffy::taffy;
use egui_taffy::{tui, AsTuiBuilder, TuiBuilderLogic};
use taffy::prelude::*;

use crate::state::AppState;

pub enum SubmitAction {
    None,
    Submit,
    RemoveFile(usize),
    RefreshQueue,
}

pub fn submit_panel(ui: &mut egui::Ui, state: &mut AppState) -> SubmitAction {
    let mut action = SubmitAction::None;

    tui(ui, "submit_layout")
        .reserve_available_space()
        .style(taffy::Style {
            flex_direction: taffy::FlexDirection::Row,
            gap: Size { width: length(12.), height: length(0.) },
            ..Default::default()
        })
        .show(|tui| {
            // Left column: builder
            tui.tui()
                .mut_style(|s| {
                    s.flex_grow = 1.0;
                    s.min_size.width = length(250.);
                })
                .ui(|ui| {
                    ui.heading("Submit Capture");
                    ui.add_space(4.0);

                    egui::Grid::new("submit_fields")
                        .num_columns(2)
                        .spacing([8.0, 4.0])
                        .show(ui, |ui| {
                            ui.label("Title:");
                            ui.text_edit_singleline(&mut state.submit_title);
                            ui.end_row();

                            ui.label("URL:");
                            ui.text_edit_singleline(&mut state.submit_url);
                            ui.end_row();

                            ui.label("Description:");
                            ui.text_edit_singleline(&mut state.submit_description);
                            ui.end_row();

                            ui.label("Source type:");
                            ui.text_edit_singleline(&mut state.submit_source_type);
                            ui.end_row();
                        });

                    ui.add_space(4.0);

                    // File list
                    if !state.submit_files.is_empty() {
                        ui.label(format!("Files ({})", state.submit_files.len()));
                        let mut remove_idx = None;
                        for (i, file) in state.submit_files.iter().enumerate() {
                            ui.horizontal(|ui| {
                                ui.monospace(&file.name);
                                if ui.small_button("\u{2715}").clicked() {
                                    remove_idx = Some(i);
                                }
                            });
                        }
                        if let Some(idx) = remove_idx {
                            action = SubmitAction::RemoveFile(idx);
                        }
                    } else {
                        ui.colored_label(
                            ui.visuals().weak_text_color(),
                            "Drop files here or use the file dialog",
                        );
                    }

                    ui.add_space(4.0);

                    ui.horizontal(|ui| {
                        let can_submit = !state.submit_title.is_empty()
                            || !state.submit_url.is_empty()
                            || !state.submit_files.is_empty();

                        if ui
                            .add_enabled(can_submit, egui::Button::new("Submit"))
                            .clicked()
                        {
                            action = SubmitAction::Submit;
                        }

                        if let Some(status) = &state.submit_status {
                            ui.label(status);
                        }
                    });
                });

            // Right column: queue
            tui.tui()
                .mut_style(|s| {
                    s.flex_grow = 1.0;
                    s.min_size.width = length(200.);
                })
                .ui(|ui| {
                    ui.horizontal(|ui| {
                        ui.heading("Pending Captures");
                        if ui.small_button("\u{21BB}").clicked() {
                            action = SubmitAction::RefreshQueue;
                        }
                    });
                    ui.add_space(4.0);

                    if state.submissions.is_empty() {
                        ui.colored_label(ui.visuals().weak_text_color(), "No pending captures");
                    } else {
                        egui::ScrollArea::vertical()
                            .max_height(200.0)
                            .show(ui, |ui| {
                                for entry in &state.submissions {
                                    ui.group(|ui| {
                                        ui.horizontal(|ui| {
                                            ui.strong(&entry.title);
                                            if !entry.files.is_empty() {
                                                ui.weak(format!(
                                                    "({} file{})",
                                                    entry.files.len(),
                                                    if entry.files.len() == 1 { "" } else { "s" }
                                                ));
                                            }
                                        });
                                        if let Some(url) = &entry.url {
                                            ui.weak(url);
                                        }
                                        if !entry.capture_date.is_empty() {
                                            ui.weak(&entry.capture_date);
                                        }
                                    });
                                }
                            });
                    }
                });
        });

    action
}
