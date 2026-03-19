use std::path::PathBuf;

use clap::Parser;

mod app;
mod state;
mod views;
mod widgets;

#[derive(Parser)]
#[command(name = "athenaeum", about = "Athenaeum corpus management frontend")]
struct Cli {
    /// Path to the corpus directory
    #[arg(short, long, env = "ATHENAEUM_CORPUS")]
    corpus: PathBuf,
}

fn main() -> anyhow::Result<()> {
    tracing_subscriber::fmt()
        .with_env_filter(tracing_subscriber::EnvFilter::from_default_env())
        .init();

    let cli = Cli::parse();

    let corpus_path = cli.corpus.canonicalize().unwrap_or(cli.corpus.clone());
    let corpus_name = corpus_path
        .file_name()
        .map(|n| n.to_string_lossy().to_string())
        .unwrap_or_else(|| "corpus".to_string());

    let options = eframe::NativeOptions {
        viewport: egui::ViewportBuilder::default()
            .with_inner_size([1400.0, 900.0])
            .with_title(format!("Athenaeum — {corpus_name}")),
        ..Default::default()
    };

    eframe::run_native(
        "Athenaeum",
        options,
        Box::new(move |_cc| Ok(Box::new(app::AtheneumApp::new(corpus_path)))),
    )
    .map_err(|e| anyhow::anyhow!("eframe error: {e}"))
}
