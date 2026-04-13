//! Catppuccin themes for egui.
//! Adapted from https://github.com/catppuccin/egui (MIT license).

use egui::Color32;

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Theme {
    EguiDark,
    Latte,
    Frappe,
    Macchiato,
    Mocha,
}

impl Theme {
    pub const ALL: &[Theme] = &[
        Theme::EguiDark,
        Theme::Latte,
        Theme::Frappe,
        Theme::Macchiato,
        Theme::Mocha,
    ];

    pub fn label(&self) -> &'static str {
        match self {
            Theme::EguiDark => "egui Dark",
            Theme::Latte => "Latte",
            Theme::Frappe => "Frappe",
            Theme::Macchiato => "Macchiato",
            Theme::Mocha => "Mocha",
        }
    }
}

struct Palette {
    rosewater: Color32,
    maroon: Color32,
    peach: Color32,
    blue: Color32,
    text: Color32,
    overlay1: Color32,
    surface2: Color32,
    surface1: Color32,
    surface0: Color32,
    base: Color32,
    mantle: Color32,
    crust: Color32,
    is_light: bool,
}

const LATTE: Palette = Palette {
    rosewater: Color32::from_rgb(220, 138, 120),
    maroon: Color32::from_rgb(230, 69, 83),
    peach: Color32::from_rgb(254, 100, 11),
    blue: Color32::from_rgb(30, 102, 245),
    text: Color32::from_rgb(76, 79, 105),
    overlay1: Color32::from_rgb(140, 143, 161),
    surface2: Color32::from_rgb(172, 176, 190),
    surface1: Color32::from_rgb(188, 192, 204),
    surface0: Color32::from_rgb(204, 208, 218),
    base: Color32::from_rgb(239, 241, 245),
    mantle: Color32::from_rgb(230, 233, 239),
    crust: Color32::from_rgb(220, 224, 232),
    is_light: true,
};

const FRAPPE: Palette = Palette {
    rosewater: Color32::from_rgb(242, 213, 207),
    maroon: Color32::from_rgb(234, 153, 156),
    peach: Color32::from_rgb(239, 159, 118),
    blue: Color32::from_rgb(140, 170, 238),
    text: Color32::from_rgb(198, 208, 245),
    overlay1: Color32::from_rgb(131, 139, 167),
    surface2: Color32::from_rgb(98, 104, 128),
    surface1: Color32::from_rgb(81, 87, 109),
    surface0: Color32::from_rgb(65, 69, 89),
    base: Color32::from_rgb(48, 52, 70),
    mantle: Color32::from_rgb(41, 44, 60),
    crust: Color32::from_rgb(35, 38, 52),
    is_light: false,
};

const MACCHIATO: Palette = Palette {
    rosewater: Color32::from_rgb(244, 219, 214),
    maroon: Color32::from_rgb(238, 153, 160),
    peach: Color32::from_rgb(245, 169, 127),
    blue: Color32::from_rgb(138, 173, 244),
    text: Color32::from_rgb(202, 211, 245),
    overlay1: Color32::from_rgb(128, 135, 162),
    surface2: Color32::from_rgb(91, 96, 120),
    surface1: Color32::from_rgb(73, 77, 100),
    surface0: Color32::from_rgb(54, 58, 79),
    base: Color32::from_rgb(36, 39, 58),
    mantle: Color32::from_rgb(30, 32, 48),
    crust: Color32::from_rgb(24, 25, 38),
    is_light: false,
};

const MOCHA: Palette = Palette {
    rosewater: Color32::from_rgb(245, 224, 220),
    maroon: Color32::from_rgb(235, 160, 172),
    peach: Color32::from_rgb(250, 179, 135),
    blue: Color32::from_rgb(137, 180, 250),
    text: Color32::from_rgb(205, 214, 244),
    overlay1: Color32::from_rgb(127, 132, 156),
    surface2: Color32::from_rgb(88, 91, 112),
    surface1: Color32::from_rgb(69, 71, 90),
    surface0: Color32::from_rgb(49, 50, 68),
    base: Color32::from_rgb(30, 30, 46),
    mantle: Color32::from_rgb(24, 24, 37),
    crust: Color32::from_rgb(17, 17, 27),
    is_light: false,
};

fn widget_visuals(
    old: egui::style::WidgetVisuals,
    palette: &Palette,
    bg_fill: Color32,
) -> egui::style::WidgetVisuals {
    egui::style::WidgetVisuals {
        bg_fill,
        weak_bg_fill: bg_fill,
        bg_stroke: egui::Stroke { color: palette.overlay1, ..old.bg_stroke },
        fg_stroke: egui::Stroke { color: palette.text, ..old.fg_stroke },
        ..old
    }
}

fn apply_palette(ctx: &egui::Context, palette: &Palette) {
    let old = ctx.global_style().visuals.clone();
    let shadow_alpha = if palette.is_light { 25 } else { 96 };

    ctx.set_visuals(egui::Visuals {
        dark_mode: !palette.is_light,
        hyperlink_color: palette.rosewater,
        faint_bg_color: palette.surface0,
        extreme_bg_color: palette.crust,
        code_bg_color: palette.mantle,
        warn_fg_color: palette.peach,
        error_fg_color: palette.maroon,
        window_fill: palette.base,
        panel_fill: palette.base,
        window_stroke: egui::Stroke { color: palette.overlay1, ..old.window_stroke },
        widgets: egui::style::Widgets {
            noninteractive: widget_visuals(old.widgets.noninteractive, palette, palette.base),
            inactive: widget_visuals(old.widgets.inactive, palette, palette.surface0),
            hovered: widget_visuals(old.widgets.hovered, palette, palette.surface2),
            active: widget_visuals(old.widgets.active, palette, palette.surface1),
            open: widget_visuals(old.widgets.open, palette, palette.surface0),
        },
        selection: egui::style::Selection {
            bg_fill: palette.blue.linear_multiply(if palette.is_light { 0.4 } else { 0.2 }),
            stroke: egui::Stroke { color: palette.text, ..old.selection.stroke },
        },
        window_shadow: egui::Shadow {
            color: Color32::from_black_alpha(shadow_alpha),
            ..old.window_shadow
        },
        popup_shadow: egui::Shadow {
            color: Color32::from_black_alpha(shadow_alpha),
            ..old.popup_shadow
        },
        ..old
    });
}

pub fn apply(ctx: &egui::Context, theme: Theme) {
    match theme {
        Theme::EguiDark => ctx.set_visuals(egui::Visuals::dark()),
        Theme::Latte => apply_palette(ctx, &LATTE),
        Theme::Frappe => apply_palette(ctx, &FRAPPE),
        Theme::Macchiato => apply_palette(ctx, &MACCHIATO),
        Theme::Mocha => apply_palette(ctx, &MOCHA),
    }
}
