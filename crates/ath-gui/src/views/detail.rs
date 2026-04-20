use ath_core::api_types::RecordDetail;
use ath_core::model::{Frontmatter, RecordType, Status};
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
pub fn detail_content(ui: &mut egui::Ui, detail: &RecordDetail, corpus: &str, md_cache: &mut egui_commonmark::CommonMarkCache) -> DetailActions {
    let mut nav_requests = Vec::new();
    let mut artifact_requests = Vec::new();

    let record = &detail.record;
    let fm = &record.frontmatter;

    egui::ScrollArea::vertical()
        .auto_shrink([false; 2])
        .show(ui, |ui| {
            // -- Rich header --
            record_header(ui, fm);

            // -- Body (promoted to top, right after header) --
            if !record.body.is_empty() {
                ui.add_space(8.0);
                egui_commonmark::CommonMarkViewer::new()
                    .show(ui, md_cache, &record.body);
                ui.add_space(8.0);
                ui.separator();
            }

            // -- Type-specific collapsible sections --
            match fm.record_type {
                RecordType::Source => source_detail(ui, fm, detail, corpus, &mut nav_requests, &mut artifact_requests),
                RecordType::Document => document_detail(ui, fm, detail, corpus, &mut nav_requests, &mut artifact_requests),
            }

            // -- Shared collapsible sections: part_of, same_as, issues, extended --
            shared_sections(ui, fm, detail, &mut nav_requests);
        });

    DetailActions {
        nav_requests,
        artifact_requests,
    }
}

// ---------------------------------------------------------------------------
// Header
// ---------------------------------------------------------------------------

/// Normalization confidence as a colored badge.
fn norm_badge(confidence: f64) -> (egui::Color32, &'static str) {
    if confidence >= 0.9 {
        (egui::Color32::from_rgb(0x40, 0xA0, 0x2B), "high")
    } else if confidence >= 0.7 {
        (egui::Color32::from_rgb(0xC0, 0x9A, 0x20), "medium")
    } else if confidence > 0.0 {
        (egui::Color32::from_rgb(0xD2, 0x6A, 0x20), "low")
    } else {
        (egui::Color32::from_rgb(0x88, 0x88, 0x88), "none")
    }
}

fn status_color(status: Status) -> egui::Color32 {
    match status {
        Status::Normalized => egui::Color32::from_rgb(0x40, 0xA0, 0x2B),
        Status::Draft => egui::Color32::from_rgb(0xC0, 0x9A, 0x20),
        Status::Stub => egui::Color32::from_rgb(0x88, 0x88, 0x88),
    }
}

fn type_color(rt: RecordType) -> egui::Color32 {
    match rt {
        RecordType::Source => egui::Color32::from_rgb(70, 130, 200),
        RecordType::Document => egui::Color32::from_rgb(70, 180, 100),
    }
}

/// Rich header with title, badges, and key metadata.
fn record_header(ui: &mut egui::Ui, fm: &Frontmatter) {
    ui.heading(&fm.title);

    // Badge row
    ui.horizontal_wrapped(|ui| {
        ui.spacing_mut().item_spacing.x = 8.0;

        // Record type
        ui.colored_label(type_color(fm.record_type), fm.record_type.to_string());

        // Content type
        if !fm.content_type.is_empty() {
            ui.label(&fm.content_type);
        }

        // Status
        ui.colored_label(status_color(fm.status), fm.status.to_string());

        // Normalization confidence badge
        let (norm_color, norm_label) = norm_badge(fm.normalization_confidence);
        ui.colored_label(
            norm_color,
            format!("norm: {} ({:.0}%)", norm_label, fm.normalization_confidence * 100.0),
        );

        // Credibility tier
        if let Some(tier) = &fm.credibility_tier {
            ui.label(tier);
        }
    });

    // Key dates row
    let has_dates = fm.capture_date.is_some() || fm.date_published.is_some() || fm.normalization_date.is_some();
    if has_dates {
        ui.horizontal_wrapped(|ui| {
            ui.spacing_mut().item_spacing.x = 12.0;
            if let Some(date) = fm.capture_date {
                ui.weak(format!("captured: {date}"));
            }
            if let Some(date) = fm.date_published {
                ui.weak(format!("published: {date}"));
            }
            if let Some(date) = fm.normalization_date {
                ui.weak(format!("normalized: {date}"));
            }
        });
    }

    // UUID row
    ui.horizontal(|ui| {
        ui.monospace(fm.uuid.to_string());
        if ui.small_button("Copy").clicked() {
            ui.ctx().copy_text(fm.uuid.to_string());
        }
    });

    ui.separator();

    // Description
    if !fm.description.is_empty() {
        ui.label(&fm.description);
        ui.add_space(4.0);
    }

    // Tags
    if !fm.tags.is_empty() {
        ui.horizontal_wrapped(|ui| {
            ui.spacing_mut().item_spacing.x = 6.0;
            for tag in &fm.tags {
                ui.weak(format!("#{tag}"));
            }
        });
        ui.add_space(4.0);
    }
}

// ---------------------------------------------------------------------------
// Source detail (collapsible sections)
// ---------------------------------------------------------------------------

fn source_detail(
    ui: &mut egui::Ui,
    fm: &Frontmatter,
    detail: &RecordDetail,
    corpus: &str,
    nav: &mut Vec<Uuid>,
    artifacts: &mut Vec<ArtifactRequest>,
) {
    // Origin
    let has_origin = fm.origin_url.is_some()
        || fm.origin_name.is_some()
        || fm.author.is_some()
        || fm.date_published.is_some()
        || fm.capture_date.is_some()
        || fm.original_filename.is_some();

    if has_origin {
        egui::CollapsingHeader::new("Origin")
            .default_open(false)
            .show(ui, |ui| {
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
    }

    // Conversion
    if fm.conversion_method.is_some() || fm.conversion_tool.is_some() || fm.conversion_date.is_some() {
        egui::CollapsingHeader::new("Conversion")
            .default_open(false)
            .show(ui, |ui| {
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

    // Normalization
    egui::CollapsingHeader::new("Normalization")
        .default_open(false)
        .show(ui, |ui| {
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
        egui::CollapsingHeader::new(format!("Artifacts ({})", fm.artifact_refs.len()))
            .default_open(false)
            .show(ui, |ui| {
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

    // Parent documents
    if !detail.parents.is_empty() {
        egui::CollapsingHeader::new(format!("Included in Documents ({})", detail.parents.len()))
            .default_open(false)
            .show(ui, |ui| {
                for parent in &detail.parents {
                    let label = format!("{} \u{2014} {}", parent.title, parent.content_type);
                    if ui.link(&label).clicked() {
                        nav.push(parent.uuid);
                    }
                }
            });
    }
}

// ---------------------------------------------------------------------------
// Document detail (collapsible sections)
// ---------------------------------------------------------------------------

fn document_detail(
    ui: &mut egui::Ui,
    fm: &Frontmatter,
    detail: &RecordDetail,
    corpus: &str,
    nav: &mut Vec<Uuid>,
    artifacts: &mut Vec<ArtifactRequest>,
) {
    // Composition
    if fm.merge_rationale.is_some() || !detail.children.is_empty() {
        egui::CollapsingHeader::new(format!("Composition ({})", detail.children.len()))
            .default_open(false)
            .show(ui, |ui| {
                if let Some(rationale) = &fm.merge_rationale {
                    ui.label(rationale);
                    ui.add_space(4.0);
                }

                for child in &detail.children {
                    ui.horizontal(|ui| {
                        let tc = match child.record_type.as_str() {
                            "source" => egui::Color32::from_rgb(70, 130, 200),
                            _ => egui::Color32::from_rgb(70, 180, 100),
                        };
                        ui.colored_label(tc, &child.record_type);
                        let label = format!("{} \u{2014} {}", child.title, child.content_type);
                        if ui.link(&label).clicked() {
                            nav.push(child.uuid);
                        }
                    });
                }
            });
    }

    // Normalization
    egui::CollapsingHeader::new("Normalization")
        .default_open(false)
        .show(ui, |ui| {
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
        egui::CollapsingHeader::new(format!("Assets ({})", fm.asset_refs.len()))
            .default_open(false)
            .show(ui, |ui| {
                if let Some(store) = &fm.asset_store {
                    ui.weak(format!("Store: {store}"));
                }
                for aref in &fm.asset_refs {
                    ui.horizontal(|ui| {
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

    // Parent documents
    if !detail.parents.is_empty() {
        egui::CollapsingHeader::new(format!("Included in Documents ({})", detail.parents.len()))
            .default_open(false)
            .show(ui, |ui| {
                for parent in &detail.parents {
                    let label = format!("{} \u{2014} {}", parent.title, parent.content_type);
                    if ui.link(&label).clicked() {
                        nav.push(parent.uuid);
                    }
                }
            });
    }
}

// ---------------------------------------------------------------------------
// Shared collapsible sections: part_of, same_as, issues, extended
// ---------------------------------------------------------------------------

fn shared_sections(
    ui: &mut egui::Ui,
    fm: &Frontmatter,
    _detail: &RecordDetail,
    nav: &mut Vec<Uuid>,
) {
    // Part of (instance-of classification)
    if !fm.part_of.is_empty() {
        egui::CollapsingHeader::new(format!("Part of ({})", fm.part_of.len()))
            .default_open(false)
            .show(ui, |ui| {
                for target in &fm.part_of {
                    if ui.link(target.to_string()).clicked() {
                        nav.push(*target);
                    }
                }
            });
    }

    // Same as (identity equivalence)
    if !fm.same_as.is_empty() {
        egui::CollapsingHeader::new(format!("Same as ({})", fm.same_as.len()))
            .default_open(false)
            .show(ui, |ui| {
                for target in &fm.same_as {
                    if ui.link(target.to_string()).clicked() {
                        nav.push(*target);
                    }
                }
            });
    }

    // Issues
    if !fm.issues.is_empty() {
        egui::CollapsingHeader::new(format!("Issues ({})", fm.issues.len()))
            .default_open(false)
            .show(ui, |ui| {
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
        egui::CollapsingHeader::new(format!("Extended Fields ({})", fm.extended.len()))
            .default_open(false)
            .show(ui, |ui| {
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
