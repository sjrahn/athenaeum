use std::path::PathBuf;
use std::sync::Arc;

use axum::extract::{Path, Query, State};
use axum::http::Method;
use axum::response::Json;
use axum::routing::get;
use axum::Router;
use tower_http::cors::{Any, CorsLayer};
use tower_http::services::ServeDir;

use ath_core::corpus::Corpus;
use ath_core::db::{CorpusDb, CorpusInfo, FacetsResponse, QueryParams, QueryResult, RecordDetail};

const CORPUS_PATHS: &[(&str, &str)] = &[
    ("corpus-private", "../corpus-private"),
    ("corpus-public", "../corpus-public"),
];

type AppState = Arc<CorpusDb>;

async fn get_corpora(State(db): State<AppState>) -> Json<Vec<CorpusInfo>> {
    Json(db.list_corpora().unwrap_or_default())
}

#[derive(serde::Deserialize)]
struct FacetsParams {
    corpus: String,
}

async fn get_facets(
    State(db): State<AppState>,
    Query(params): Query<FacetsParams>,
) -> Json<FacetsResponse> {
    Json(db.facets(&params.corpus).unwrap_or_else(|_| FacetsResponse {
        content_types: vec![],
        statuses: vec![],
        tags: vec![],
        origin_names: vec![],
        credibility_tiers: vec![],
    }))
}

async fn get_records(
    State(db): State<AppState>,
    Query(params): Query<QueryParams>,
) -> Json<QueryResult> {
    Json(
        db.query_records(&params)
            .unwrap_or_else(|e| {
                tracing::error!(%e, "query_records failed");
                QueryResult {
                    total: 0,
                    records: vec![],
                }
            }),
    )
}

async fn get_record(
    State(db): State<AppState>,
    Path(uuid_str): Path<String>,
) -> Json<Option<RecordDetail>> {
    let uuid = match uuid_str.parse() {
        Ok(u) => u,
        Err(_) => return Json(None),
    };
    Json(db.get_record(uuid).unwrap_or(None))
}

#[tokio::main]
async fn main() -> anyhow::Result<()> {
    tracing_subscriber::fmt()
        .with_env_filter(tracing_subscriber::EnvFilter::from_default_env())
        .init();

    let db = CorpusDb::open_memory()?;

    for (name, path) in CORPUS_PATHS {
        let corpus_path = PathBuf::from(path);
        match Corpus::load(&corpus_path) {
            Ok(corpus) => {
                tracing::info!(
                    name,
                    path = %corpus_path.display(),
                    records = corpus.len(),
                    "loaded corpus"
                );
                db.insert_corpus(name, &corpus.records)?;
                tracing::info!(name, "inserted into database");
            }
            Err(e) => {
                tracing::warn!(name, path = %corpus_path.display(), %e, "skipping corpus");
            }
        }
    }

    let state: AppState = Arc::new(db);

    let cors = CorsLayer::new()
        .allow_methods([Method::GET])
        .allow_origin(Any);

    let static_dir = std::env::var("ATHENAEUM_STATIC_DIR")
        .unwrap_or_else(|_| "crates/ath-gui/dist".to_string());

    let app = Router::new()
        .route("/api/corpora", get(get_corpora))
        .route("/api/facets", get(get_facets))
        .route("/api/records", get(get_records))
        .route("/api/records/{uuid}", get(get_record))
        .layer(cors)
        .fallback_service(ServeDir::new(&static_dir))
        .with_state(state);

    let addr = "0.0.0.0:8080";
    tracing::info!("listening on http://{addr}");

    let listener = tokio::net::TcpListener::bind(addr).await?;
    axum::serve(listener, app).await?;

    Ok(())
}
