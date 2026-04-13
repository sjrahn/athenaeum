//! Font configuration for the Athenaeum viewer.

const FIRA_CODE: &[u8] = include_bytes!("../fonts/FiraCode-Regular.ttf");

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Font {
    Proportional,
    FiraCode,
}

impl Font {
    pub const ALL: &[Font] = &[Font::Proportional, Font::FiraCode];

    pub fn label(&self) -> &'static str {
        match self {
            Font::Proportional => "Default",
            Font::FiraCode => "Fira Code",
        }
    }
}

pub const DEFAULT_SIZE: f32 = 14.0;
pub const MIN_SIZE: f32 = 8.0;
pub const MAX_SIZE: f32 = 24.0;
pub const SIZE_STEP: f32 = 1.0;

pub fn apply(ctx: &egui::Context, font: Font) {
    let mut fonts = egui::FontDefinitions::default();

    // Always register Fira Code so it's available
    fonts.font_data.insert(
        "FiraCode".to_owned(),
        std::sync::Arc::new(egui::FontData::from_static(FIRA_CODE)),
    );

    match font {
        Font::Proportional => {
            // Default egui fonts; just make Fira Code available as monospace fallback
            fonts
                .families
                .entry(egui::FontFamily::Monospace)
                .or_default()
                .insert(0, "FiraCode".to_owned());
        }
        Font::FiraCode => {
            // Fira Code as the primary font for both proportional and monospace
            fonts
                .families
                .entry(egui::FontFamily::Proportional)
                .or_default()
                .insert(0, "FiraCode".to_owned());
            fonts
                .families
                .entry(egui::FontFamily::Monospace)
                .or_default()
                .insert(0, "FiraCode".to_owned());
        }
    }

    ctx.set_fonts(fonts);
}

pub fn apply_size(ctx: &egui::Context, size: f32) {
    use egui::{FontId, TextStyle, FontFamily};

    let proportional = FontFamily::Proportional;
    let monospace = FontFamily::Monospace;

    ctx.global_style_mut(|style| {
        style.text_styles.insert(TextStyle::Small, FontId::new(size * 0.75, proportional.clone()));
        style.text_styles.insert(TextStyle::Body, FontId::new(size, proportional.clone()));
        style.text_styles.insert(TextStyle::Monospace, FontId::new(size, monospace));
        style.text_styles.insert(TextStyle::Button, FontId::new(size, proportional.clone()));
        style.text_styles.insert(TextStyle::Heading, FontId::new(size * 1.43, proportional));
    });
}
