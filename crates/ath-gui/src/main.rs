mod app;
mod state;
mod views;
mod widgets;

const DEFAULT_SERVER: &str = "http://127.0.0.1:8080";

#[cfg(not(target_arch = "wasm32"))]
fn main() -> anyhow::Result<()> {
    tracing_subscriber::fmt()
        .with_env_filter(tracing_subscriber::EnvFilter::from_default_env())
        .init();

    let server_url = std::env::var("ATHENAEUM_SERVER").unwrap_or_else(|_| DEFAULT_SERVER.to_string());

    let options = eframe::NativeOptions {
        viewport: egui::ViewportBuilder::default()
            .with_inner_size([1400.0, 900.0])
            .with_title("Athenaeum"),
        ..Default::default()
    };

    eframe::run_native(
        "Athenaeum",
        options,
        Box::new(move |_cc| Ok(Box::new(app::AtheneumApp::new(server_url)))),
    )
    .map_err(|e| anyhow::anyhow!("eframe error: {e}"))
}

#[cfg(target_arch = "wasm32")]
fn main() {
    use tracing_subscriber::layer::SubscriberExt;
    use tracing_subscriber::util::SubscriberInitExt;
    use wasm_bindgen::JsCast;

    tracing_subscriber::registry()
        .with(
            tracing_subscriber::fmt::layer()
                .with_writer(tracing_web::MakeConsoleWriter)
                .without_time(),
        )
        .init();

    let web_options = eframe::WebOptions::default();

    wasm_bindgen_futures::spawn_local(async {
        let runner = eframe::WebRunner::new();

        // Get the canvas element from the DOM
        let document = web_sys::window()
            .expect("no window")
            .document()
            .expect("no document");
        let canvas = document
            .get_element_by_id("athenaeum_canvas")
            .expect("no canvas element")
            .dyn_into::<web_sys::HtmlCanvasElement>()
            .expect("not a canvas element");

        // Derive server URL from the page origin
        let server_url = web_sys::window()
            .and_then(|w| w.location().origin().ok())
            .unwrap_or_else(|| DEFAULT_SERVER.to_string());

        runner
            .start(
                canvas,
                web_options,
                Box::new(move |_cc| Ok(Box::new(app::AtheneumApp::new(server_url)))),
            )
            .await
            .expect("failed to start eframe");
    });
}
