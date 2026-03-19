use ath_core::model::RecordType;

use crate::state::AppState;

pub fn detail_view(ui: &mut egui::Ui, state: &mut AppState) {
    let Some(uuid) = state.selected_record else {
        ui.centered_and_justified(|ui| {
            ui.heading("Select a record from the sidebar");
        });
        return;
    };

    let Some(record) = state.corpus.get(&uuid) else {
        ui.colored_label(egui::Color32::RED, "Selected record not found.");
        state.selected_record = None;
        return;
    };

    let fm = &record.frontmatter;

    egui::ScrollArea::vertical()
        .auto_shrink([false; 2])
        .show(ui, |ui| {
            // Header
            ui.heading(&fm.title);
            ui.horizontal(|ui| {
                // UUID (monospace)
                ui.monospace(fm.uuid.to_string());
                if ui.small_button("Copy").clicked() {
                    ui.ctx().copy_text(fm.uuid.to_string());
                }
            });

            ui.add_space(4.0);

            // Badges row
            ui.horizontal(|ui| {
                let type_color = match fm.record_type {
                    RecordType::Source => egui::Color32::from_rgb(70, 130, 200),
                    RecordType::Document => egui::Color32::from_rgb(70, 180, 100),
                };
                ui.colored_label(type_color, fm.record_type.to_string());
                ui.label("|");
                ui.label(&fm.content_type);
                ui.label("|");
                ui.label(fm.status.to_string());
                if let Some(tier) = &fm.credibility_tier {
                    ui.label("|");
                    ui.label(tier);
                }
            });

            ui.separator();

            // Description
            if !fm.description.is_empty() {
                ui.label(&fm.description);
                ui.add_space(8.0);
            }

            // Tags
            if !fm.tags.is_empty() {
                ui.horizontal_wrapped(|ui| {
                    ui.strong("Tags:");
                    for tag in &fm.tags {
                        ui.label(format!("#{tag}"));
                    }
                });
                ui.add_space(4.0);
            }

            // Metadata grid
            ui.group(|ui| {
                ui.heading("Metadata");
                egui::Grid::new("metadata_grid")
                    .num_columns(2)
                    .spacing([20.0, 4.0])
                    .show(ui, |ui| {
                        // Source-specific
                        if let Some(url) = &fm.origin_url {
                            ui.strong("Origin URL:");
                            ui.hyperlink(url);
                            ui.end_row();
                        }
                        if let Some(name) = &fm.origin_name {
                            ui.strong("Origin:");
                            ui.label(name);
                            ui.end_row();
                        }
                        if let Some(date) = fm.capture_date {
                            ui.strong("Capture Date:");
                            ui.label(date.to_string());
                            ui.end_row();
                        }
                        if let Some(author) = &fm.author {
                            ui.strong("Author:");
                            ui.label(author);
                            ui.end_row();
                        }
                        if let Some(date) = fm.date_published {
                            ui.strong("Published:");
                            ui.label(date.to_string());
                            ui.end_row();
                        }

                        // Quality
                        ui.strong("Confidence:");
                        ui.add(
                            egui::ProgressBar::new(fm.normalization_confidence as f32)
                                .text(format!("{:.0}%", fm.normalization_confidence * 100.0)),
                        );
                        ui.end_row();

                        if let Some(model) = &fm.normalization_model {
                            ui.strong("Model:");
                            ui.label(model);
                            ui.end_row();
                        }
                        if let Some(date) = fm.normalization_date {
                            ui.strong("Normalized:");
                            ui.label(date.to_string());
                            ui.end_row();
                        }

                        // Pipeline
                        if let Some(method) = &fm.conversion_method {
                            ui.strong("Conversion:");
                            ui.label(method);
                            ui.end_row();
                        }
                        if let Some(tool) = &fm.conversion_tool {
                            ui.strong("Tool:");
                            ui.label(tool);
                            ui.end_row();
                        }
                    });
            });

            // Extended fields
            if !fm.extended.is_empty() {
                ui.add_space(8.0);
                ui.group(|ui| {
                    ui.heading("Extended Fields");
                    egui::Grid::new("extended_grid")
                        .num_columns(2)
                        .spacing([20.0, 4.0])
                        .show(ui, |ui| {
                            for (key, value) in &fm.extended {
                                ui.strong(key);
                                ui.label(format_yaml_value(value));
                                ui.end_row();
                            }
                        });
                });
            }

            // Constituents (document records)
            if let Some(constituents) = &fm.constituents {
                ui.add_space(8.0);
                ui.group(|ui| {
                    ui.heading("Constituents");
                    for child_uuid in constituents {
                        let label = if let Some(child) = state.corpus.get(child_uuid) {
                            format!("{} — {}", child.frontmatter.title, child.frontmatter.content_type)
                        } else {
                            format!("{child_uuid} (not found)")
                        };
                        if ui.link(&label).clicked() {
                            state.selected_record = Some(*child_uuid);
                        }
                    }
                });
            }

            // Parent documents (records that list this one as a constituent)
            let parents = state.dag.parents(&uuid);
            if !parents.is_empty() {
                ui.add_space(8.0);
                ui.group(|ui| {
                    ui.heading("Parent Documents");
                    for parent_uuid in &parents {
                        let label = if let Some(parent) = state.corpus.get(parent_uuid) {
                            format!("{} — {}", parent.frontmatter.title, parent.frontmatter.content_type)
                        } else {
                            parent_uuid.to_string()
                        };
                        if ui.link(&label).clicked() {
                            state.selected_record = Some(*parent_uuid);
                        }
                    }
                });
            }

            // Relations
            if !fm.relations.is_empty() {
                ui.add_space(8.0);
                ui.group(|ui| {
                    ui.heading("Relations");
                    for rel in &fm.relations {
                        ui.horizontal(|ui| {
                            ui.strong(&rel.relation_type);
                            if let Some(target) = rel.target {
                                let label = if let Some(target_rec) = state.corpus.get(&target) {
                                    target_rec.frontmatter.title.clone()
                                } else {
                                    target.to_string()
                                };
                                if ui.link(&label).clicked() {
                                    state.selected_record = Some(target);
                                }
                            } else if let Some(unresolved) = &rel.unresolved {
                                ui.weak(format!("(unresolved: {unresolved})"));
                            }
                        });
                    }
                });
            }

            // Issues
            if !fm.issues.is_empty() {
                ui.add_space(8.0);
                ui.group(|ui| {
                    ui.heading("Issues");
                    for issue in &fm.issues {
                        ui.horizontal(|ui| {
                            let severity_color = match issue.severity.as_str() {
                                "critical" => egui::Color32::from_rgb(220, 50, 50),
                                "major" => egui::Color32::from_rgb(220, 150, 50),
                                _ => egui::Color32::from_rgb(150, 150, 50),
                            };
                            ui.colored_label(severity_color, &issue.severity);
                            ui.label(&issue.issue_type);
                            if issue.resolved {
                                ui.weak("[resolved]");
                            }
                        });
                        ui.indent(issue.issue_type.as_str(), |ui| {
                            ui.label(&issue.description);
                        });
                    }
                });
            }

            // Artifact refs
            if !fm.artifact_refs.is_empty() {
                ui.add_space(8.0);
                ui.group(|ui| {
                    ui.heading("Artifacts");
                    for aref in &fm.artifact_refs {
                        ui.horizontal(|ui| {
                            ui.monospace(&aref.uri);
                            ui.weak(format!("sha256: {}...", &aref.sha256[..aref.sha256.len().min(16)]));
                        });
                    }
                });
            }

            // Asset refs
            if !fm.asset_refs.is_empty() {
                ui.add_space(8.0);
                ui.group(|ui| {
                    ui.heading("Assets");
                    for aref in &fm.asset_refs {
                        ui.horizontal(|ui| {
                            ui.monospace(&aref.uri);
                            if let Some(source) = &aref.source {
                                ui.weak(format!("from: {source}"));
                            }
                        });
                    }
                });
            }

            // Body
            ui.add_space(12.0);
            ui.separator();
            ui.heading("Body");
            ui.add_space(4.0);

            if record.body.is_empty() {
                ui.weak("(no body content)");
            } else {
                // Raw text display for Phase 1, markdown rendering in Phase 5
                ui.monospace(&record.body);
            }
        });
}

/// Format a serde_yaml_ng::Value for display.
fn format_yaml_value(value: &serde_yaml_ng::Value) -> String {
    match value {
        serde_yaml_ng::Value::Null => "null".to_string(),
        serde_yaml_ng::Value::Bool(b) => b.to_string(),
        serde_yaml_ng::Value::Number(n) => n.to_string(),
        serde_yaml_ng::Value::String(s) => s.clone(),
        serde_yaml_ng::Value::Sequence(seq) => {
            let items: Vec<String> = seq.iter().map(format_yaml_value).collect();
            items.join(", ")
        }
        serde_yaml_ng::Value::Mapping(map) => {
            let pairs: Vec<String> = map
                .iter()
                .map(|(k, v)| format!("{}: {}", format_yaml_value(k), format_yaml_value(v)))
                .collect();
            pairs.join(", ")
        }
        serde_yaml_ng::Value::Tagged(tagged) => format_yaml_value(&tagged.value),
    }
}
