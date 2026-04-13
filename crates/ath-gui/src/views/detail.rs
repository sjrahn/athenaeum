use ath_core::api_types::RecordDetail;
use ath_core::model::{Frontmatter, RecordType};
use uuid::Uuid;

/// Request to open an artifact/asset preview.
pub struct ArtifactRequest {
    pub corpus: String,
    pub kind: String, // "artifacts" or "assets"
    pub uuid: String,
    pub filename: String,
}

/// Actions returned by the detail view.
pub struct DetailActions {
    pub nav_requests: Vec<Uuid>,
    pub artifact_requests: Vec<ArtifactRequest>,
}

/// Render record detail content. Returns navigation and artifact open requests.
pub fn detail_content(ui: &mut egui::Ui, detail: &RecordDetail, corpus: &str) -> DetailActions {
    let mut nav_requests = Vec::new();
    let mut artifact_requests = Vec::new();

    let record = &detail.record;
    let fm = &record.frontmatter;

    egui::ScrollArea::vertical()
        .auto_shrink([false; 2])
        .show(ui, |ui| {
            // -- Shared header --
            record_header(ui, fm);

            // -- Type-specific sections --
            match fm.record_type {
                RecordType::Source => source_detail(ui, fm, detail, corpus, &mut nav_requests, &mut artifact_requests),
                RecordType::Document => document_detail(ui, fm, detail, corpus, &mut nav_requests, &mut artifact_requests),
            }

            // -- Shared footer: relations, issues, extended, body --
            shared_footer(ui, fm, detail, &record.body, &mut nav_requests);
        });

    DetailActions {
        nav_requests,
        artifact_requests,
    }
}

/// Header shared by both source and document views.
fn record_header(ui: &mut egui::Ui, fm: &Frontmatter) {
    ui.heading(&fm.title);
    ui.horizontal(|ui| {
        ui.monospace(fm.uuid.to_string());
        if ui.small_button("Copy").clicked() {
            ui.ctx().copy_text(fm.uuid.to_string());
        }
    });

    ui.add_space(4.0);

    // Badges
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
}

/// Source-specific detail view.
fn source_detail(
    ui: &mut egui::Ui,
    fm: &Frontmatter,
    detail: &RecordDetail,
    corpus: &str,
    nav: &mut Vec<Uuid>,
    artifacts: &mut Vec<ArtifactRequest>,
) {
    // Origin & capture info
    ui.group(|ui| {
        ui.heading("Origin");
        egui::Grid::new("source_origin_grid")
            .num_columns(2)
            .spacing([20.0, 4.0])
            .show(ui, |ui| {
                if let Some(url) = &fm.origin_url {
                    ui.strong("URL:");
                    ui.hyperlink(url);
                    ui.end_row();
                }
                if let Some(name) = &fm.origin_name {
                    ui.strong("Origin:");
                    ui.label(name);
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
                if let Some(date) = fm.capture_date {
                    ui.strong("Captured:");
                    ui.label(date.to_string());
                    ui.end_row();
                }
                if let Some(filename) = &fm.original_filename {
                    ui.strong("Original File:");
                    ui.label(filename);
                    ui.end_row();
                }
            });
    });

    // Conversion pipeline
    if fm.conversion_method.is_some() || fm.conversion_tool.is_some() || fm.conversion_date.is_some() {
        ui.add_space(8.0);
        ui.group(|ui| {
            ui.heading("Conversion");
            egui::Grid::new("source_conversion_grid")
                .num_columns(2)
                .spacing([20.0, 4.0])
                .show(ui, |ui| {
                    if let Some(method) = &fm.conversion_method {
                        ui.strong("Method:");
                        ui.label(method);
                        ui.end_row();
                    }
                    if let Some(tool) = &fm.conversion_tool {
                        ui.strong("Tool:");
                        ui.label(tool);
                        ui.end_row();
                    }
                    if let Some(date) = fm.conversion_date {
                        ui.strong("Date:");
                        ui.label(date.to_string());
                        ui.end_row();
                    }
                });
        });
    }

    // Normalization quality
    ui.add_space(8.0);
    ui.group(|ui| {
        ui.heading("Normalization");
        egui::Grid::new("source_norm_grid")
            .num_columns(2)
            .spacing([20.0, 4.0])
            .show(ui, |ui| {
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
                    ui.strong("Date:");
                    ui.label(date.to_string());
                    ui.end_row();
                }
            });
    });

    // Artifacts
    if !fm.artifact_refs.is_empty() {
        ui.add_space(8.0);
        ui.group(|ui| {
            ui.heading("Artifacts");
            if let Some(store) = &fm.artifact_store {
                ui.weak(format!("Store: {store}"));
            }
            for aref in &fm.artifact_refs {
                ui.horizontal(|ui| {
                    let filename = aref.uri.strip_prefix("artifacts://").unwrap_or(&aref.uri);
                    if ui.link(filename).clicked() {
                        artifacts.push(ArtifactRequest {
                            corpus: corpus.to_string(),
                            kind: "artifacts".to_string(),
                            uuid: fm.uuid.to_string(),
                            filename: filename.to_string(),
                        });
                    }
                    ui.weak(format!(
                        "sha256: {}...",
                        &aref.sha256[..aref.sha256.len().min(16)]
                    ));
                });
            }
        });
    }

    // Parent documents (documents that include this source)
    if !detail.parents.is_empty() {
        ui.add_space(8.0);
        ui.group(|ui| {
            ui.heading("Included in Documents");
            for parent in &detail.parents {
                let label = format!("{} — {}", parent.title, parent.content_type);
                if ui.link(&label).clicked() {
                    nav.push(parent.uuid);
                }
            }
        });
    }
}

/// Document-specific detail view.
fn document_detail(
    ui: &mut egui::Ui,
    fm: &Frontmatter,
    detail: &RecordDetail,
    corpus: &str,
    nav: &mut Vec<Uuid>,
    artifacts: &mut Vec<ArtifactRequest>,
) {
    // Merge info
    if fm.merge_rationale.is_some() || !detail.children.is_empty() {
        ui.group(|ui| {
            ui.heading("Composition");
            if let Some(rationale) = &fm.merge_rationale {
                ui.label(rationale);
                ui.add_space(4.0);
            }

            if !detail.children.is_empty() {
                ui.strong(format!("Constituents ({}):", detail.children.len()));
                for child in &detail.children {
                    ui.horizontal(|ui| {
                        let type_color = match child.record_type.as_str() {
                            "source" => egui::Color32::from_rgb(70, 130, 200),
                            _ => egui::Color32::from_rgb(70, 180, 100),
                        };
                        ui.colored_label(type_color, &child.record_type);
                        let label = format!("{} — {}", child.title, child.content_type);
                        if ui.link(&label).clicked() {
                            nav.push(child.uuid);
                        }
                    });
                }
            }
        });
    }

    // Normalization quality
    ui.add_space(8.0);
    ui.group(|ui| {
        ui.heading("Normalization");
        egui::Grid::new("doc_norm_grid")
            .num_columns(2)
            .spacing([20.0, 4.0])
            .show(ui, |ui| {
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
                    ui.strong("Date:");
                    ui.label(date.to_string());
                    ui.end_row();
                }
            });
    });

    // Assets
    if !fm.asset_refs.is_empty() {
        ui.add_space(8.0);
        ui.group(|ui| {
            ui.heading("Assets");
            if let Some(store) = &fm.asset_store {
                ui.weak(format!("Store: {store}"));
            }
            for aref in &fm.asset_refs {
                ui.horizontal(|ui| {
                    // Determine kind and UUID for the file serving endpoint
                    let (kind, owner_uuid, filename) = if aref.uri.starts_with("assets://") {
                        ("assets", fm.uuid.to_string(), aref.uri.strip_prefix("assets://").unwrap_or(&aref.uri).to_string())
                    } else if aref.uri.starts_with("artifacts://") {
                        let owner = aref.source.map(|u| u.to_string()).unwrap_or_else(|| fm.uuid.to_string());
                        ("artifacts", owner, aref.uri.strip_prefix("artifacts://").unwrap_or(&aref.uri).to_string())
                    } else {
                        ("assets", fm.uuid.to_string(), aref.uri.clone())
                    };

                    if ui.link(&filename).clicked() {
                        artifacts.push(ArtifactRequest {
                            corpus: corpus.to_string(),
                            kind: kind.to_string(),
                            uuid: owner_uuid,
                            filename,
                        });
                    }
                    if let Some(sha) = &aref.sha256 {
                        ui.weak(format!("sha256: {}...", &sha[..sha.len().min(16)]));
                    }
                    if let Some(source) = &aref.source {
                        ui.weak(format!("from: {source}"));
                    }
                });
            }
        });
    }

    // Parent documents (documents that include this document)
    if !detail.parents.is_empty() {
        ui.add_space(8.0);
        ui.group(|ui| {
            ui.heading("Included in Documents");
            for parent in &detail.parents {
                let label = format!("{} — {}", parent.title, parent.content_type);
                if ui.link(&label).clicked() {
                    nav.push(parent.uuid);
                }
            }
        });
    }
}

/// Footer sections shared by both types: relations, issues, extended fields, body.
fn shared_footer(
    ui: &mut egui::Ui,
    fm: &Frontmatter,
    _detail: &RecordDetail,
    body: &str,
    nav: &mut Vec<Uuid>,
) {
    // Relations
    if !fm.relations.is_empty() {
        ui.add_space(8.0);
        ui.group(|ui| {
            ui.heading("Relations");
            for rel in &fm.relations {
                ui.horizontal(|ui| {
                    ui.strong(&rel.relation_type);
                    if let Some(target) = rel.target {
                        if ui.link(target.to_string()).clicked() {
                            nav.push(target);
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

    // Body
    ui.add_space(12.0);
    ui.separator();
    ui.heading("Body");
    ui.add_space(4.0);

    if body.is_empty() {
        ui.weak("(no body content)");
    } else {
        ui.monospace(body);
    }
}

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
