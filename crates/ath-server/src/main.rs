use std::path::PathBuf;
use std::sync::Arc;

use axum::extract::{Multipart, Path, Query, State};
use axum::http::Method;
use axum::response::Json;
use axum::routing::{get, post};
use axum::Router;
use tower_http::cors::{Any, CorsLayer};
use tower_http::services::ServeDir;

use ath_core::api_types::{SubmissionEntry, SubmissionsResponse, SubmitResponse};
use ath_core::corpus::Corpus;
use ath_core::db::{CorpusDb, CorpusInfo, FacetsResponse, QueryParams, QueryResult, RecordDetail};

const CORPUS_PATHS: &[(&str, &str)] = &[
    ("corpus-private", "../corpus-private"),
    ("corpus-public", "../corpus-public"),
];

struct ServerState {
    db: CorpusDb,
    corpus_paths: Vec<(String, PathBuf)>,
}

type AppState = Arc<ServerState>;

async fn get_corpora(State(state): State<AppState>) -> Json<Vec<CorpusInfo>> {
    Json(state.db.list_corpora().unwrap_or_default())
}

#[derive(serde::Deserialize)]
struct FacetsParams {
    corpus: String,
}

async fn get_facets(
    State(state): State<AppState>,
    Query(params): Query<FacetsParams>,
) -> Json<FacetsResponse> {
    Json(
        state
            .db
            .facets(&params.corpus)
            .unwrap_or_else(|_| FacetsResponse {
                content_types: vec![],
                statuses: vec![],
                tags: vec![],
                origin_names: vec![],
                credibility_tiers: vec![],
            }),
    )
}

async fn get_records(
    State(state): State<AppState>,
    Query(params): Query<QueryParams>,
) -> Json<QueryResult> {
    Json(state.db.query_records(&params).unwrap_or_else(|e| {
        tracing::error!(%e, "query_records failed");
        QueryResult {
            total: 0,
            records: vec![],
        }
    }))
}

async fn get_record(
    State(state): State<AppState>,
    Path(uuid_str): Path<String>,
) -> Json<Option<RecordDetail>> {
    let uuid = match uuid_str.parse() {
        Ok(u) => u,
        Err(_) => return Json(None),
    };
    Json(state.db.get_record(uuid).unwrap_or(None))
}

async fn submit_capture(
    State(state): State<AppState>,
    mut multipart: Multipart,
) -> Result<Json<SubmitResponse>, axum::http::StatusCode> {
    let mut corpus_name = String::new();
    let mut title = String::new();
    let mut description = String::new();
    let mut url = String::new();
    let mut source_type = String::new();
    let mut files: Vec<(String, Vec<u8>)> = Vec::new();

    while let Some(field) = multipart
        .next_field()
        .await
        .map_err(|_| axum::http::StatusCode::BAD_REQUEST)?
    {
        let name = field.name().unwrap_or("").to_string();
        match name.as_str() {
            "corpus" => {
                corpus_name = field
                    .text()
                    .await
                    .map_err(|_| axum::http::StatusCode::BAD_REQUEST)?;
            }
            "title" => {
                title = field
                    .text()
                    .await
                    .map_err(|_| axum::http::StatusCode::BAD_REQUEST)?;
            }
            "description" => {
                description = field
                    .text()
                    .await
                    .map_err(|_| axum::http::StatusCode::BAD_REQUEST)?;
            }
            "url" => {
                url = field
                    .text()
                    .await
                    .map_err(|_| axum::http::StatusCode::BAD_REQUEST)?;
            }
            "source_type" => {
                source_type = field
                    .text()
                    .await
                    .map_err(|_| axum::http::StatusCode::BAD_REQUEST)?;
            }
            "file" => {
                let file_name = field
                    .file_name()
                    .unwrap_or("unnamed")
                    .to_string();
                let data = field
                    .bytes()
                    .await
                    .map_err(|_| axum::http::StatusCode::BAD_REQUEST)?;
                files.push((file_name, data.to_vec()));
            }
            _ => {}
        }
    }

    if corpus_name.is_empty() {
        return Err(axum::http::StatusCode::BAD_REQUEST);
    }

    // Look up corpus path
    let corpus_path = state
        .corpus_paths
        .iter()
        .find(|(name, _)| name == &corpus_name)
        .map(|(_, path)| path.clone())
        .ok_or(axum::http::StatusCode::BAD_REQUEST)?;

    // Generate slug from title or first filename
    let slug_base = if !title.is_empty() {
        slugify(&title)
    } else if let Some((name, _)) = files.first() {
        slugify(&name.rsplit('.').last().unwrap_or(name).to_string())
    } else {
        "submission".to_string()
    };

    // Ensure unique folder name
    let capture_dir = corpus_path.join("capture");
    std::fs::create_dir_all(&capture_dir)
        .map_err(|_| axum::http::StatusCode::INTERNAL_SERVER_ERROR)?;

    let folder = if capture_dir.join(&slug_base).exists() {
        let ts = chrono::Utc::now().timestamp();
        format!("{slug_base}.{ts}")
    } else {
        slug_base
    };

    let folder_path = capture_dir.join(&folder);
    std::fs::create_dir_all(&folder_path)
        .map_err(|_| axum::http::StatusCode::INTERNAL_SERVER_ERROR)?;

    // Write uploaded files
    let file_count = files.len() as u32;
    let file_names: Vec<String> = files.iter().map(|(name, _)| name.clone()).collect();
    for (name, data) in &files {
        let file_path = folder_path.join(name);
        std::fs::write(&file_path, data)
            .map_err(|_| axum::http::StatusCode::INTERNAL_SERVER_ERROR)?;
    }

    // Write metadata.json in the existing capture format
    let capture_date = chrono::Utc::now().to_rfc3339();
    let origin = if url.is_empty() {
        "file-import"
    } else {
        "web-capture"
    };

    let mut metadata = serde_json::Map::new();
    if !title.is_empty() {
        metadata.insert("title".into(), serde_json::Value::String(title));
    }
    if !description.is_empty() {
        metadata.insert(
            "description".into(),
            serde_json::Value::String(description),
        );
    }
    if !url.is_empty() {
        metadata.insert("url".into(), serde_json::Value::String(url));
    }
    if !source_type.is_empty() {
        metadata.insert(
            "source_type".into(),
            serde_json::Value::String(source_type),
        );
    }
    metadata.insert(
        "origin".into(),
        serde_json::Value::String(origin.to_string()),
    );
    metadata.insert(
        "capture_date".into(),
        serde_json::Value::String(capture_date),
    );
    if !file_names.is_empty() {
        metadata.insert(
            "files".into(),
            serde_json::Value::Array(
                file_names
                    .into_iter()
                    .map(serde_json::Value::String)
                    .collect(),
            ),
        );
    }

    let metadata_path = folder_path.join("metadata.json");
    let metadata_json = serde_json::to_string_pretty(&metadata)
        .map_err(|_| axum::http::StatusCode::INTERNAL_SERVER_ERROR)?;
    std::fs::write(&metadata_path, metadata_json)
        .map_err(|_| axum::http::StatusCode::INTERNAL_SERVER_ERROR)?;

    tracing::info!(folder = %folder, file_count, "capture staged");

    Ok(Json(SubmitResponse { folder, file_count }))
}

#[derive(serde::Deserialize)]
struct SubmissionsParams {
    corpus: String,
}

async fn get_submissions(
    State(state): State<AppState>,
    Query(params): Query<SubmissionsParams>,
) -> Result<Json<SubmissionsResponse>, axum::http::StatusCode> {
    let corpus_path = state
        .corpus_paths
        .iter()
        .find(|(name, _)| name == &params.corpus)
        .map(|(_, path)| path.clone())
        .ok_or(axum::http::StatusCode::BAD_REQUEST)?;

    let capture_dir = corpus_path.join("capture");
    let mut submissions = Vec::new();

    if let Ok(entries) = std::fs::read_dir(&capture_dir) {
        for entry in entries.flatten() {
            let path = entry.path();
            if !path.is_dir() {
                continue;
            }
            let folder = entry.file_name().to_string_lossy().to_string();
            if folder == ".gitkeep" {
                continue;
            }

            let metadata_path = path.join("metadata.json");
            if let Ok(content) = std::fs::read_to_string(&metadata_path) {
                if let Ok(meta) = serde_json::from_str::<serde_json::Value>(&content) {
                    submissions.push(SubmissionEntry {
                        folder: folder.clone(),
                        title: meta
                            .get("title")
                            .and_then(|v| v.as_str())
                            .unwrap_or(&folder)
                            .to_string(),
                        url: meta
                            .get("url")
                            .and_then(|v| v.as_str())
                            .map(|s| s.to_string()),
                        source_type: meta
                            .get("source_type")
                            .and_then(|v| v.as_str())
                            .map(|s| s.to_string()),
                        capture_date: meta
                            .get("capture_date")
                            .and_then(|v| v.as_str())
                            .unwrap_or("")
                            .to_string(),
                        files: list_capture_files(&path),
                    });
                    continue;
                }
            }

            // No metadata.json or unparseable — show with minimal info
            submissions.push(SubmissionEntry {
                folder: folder.clone(),
                title: folder,
                url: None,
                source_type: None,
                capture_date: String::new(),
                files: list_capture_files(&path),
            });
        }
    }

    // Sort newest first
    submissions.sort_by(|a, b| b.capture_date.cmp(&a.capture_date));

    Ok(Json(SubmissionsResponse { submissions }))
}

/// List non-metadata files in a capture folder.
fn list_capture_files(dir: &std::path::Path) -> Vec<String> {
    let mut files = Vec::new();
    if let Ok(entries) = std::fs::read_dir(dir) {
        for entry in entries.flatten() {
            let name = entry.file_name().to_string_lossy().to_string();
            if name != "metadata.json" && entry.path().is_file() {
                files.push(name);
            }
        }
    }
    files.sort();
    files
}

/// Convert a string to a URL-safe slug.
fn slugify(s: &str) -> String {
    s.to_lowercase()
        .chars()
        .map(|c| {
            if c.is_ascii_alphanumeric() {
                c
            } else {
                '-'
            }
        })
        .collect::<String>()
        .split('-')
        .filter(|s| !s.is_empty())
        .collect::<Vec<_>>()
        .join("-")
}

#[tokio::main]
async fn main() -> anyhow::Result<()> {
    tracing_subscriber::fmt()
        .with_env_filter(tracing_subscriber::EnvFilter::from_default_env())
        .init();

    let db = CorpusDb::open_memory()?;
    let mut corpus_paths = Vec::new();

    for (name, path) in CORPUS_PATHS {
        let corpus_path = PathBuf::from(path);
        corpus_paths.push((name.to_string(), corpus_path.clone()));
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

    let state: AppState = Arc::new(ServerState { db, corpus_paths });

    let cors = CorsLayer::new()
        .allow_methods([Method::GET, Method::POST])
        .allow_origin(Any);

    let static_dir = std::env::var("ATHENAEUM_STATIC_DIR")
        .unwrap_or_else(|_| "crates/ath-gui/dist".to_string());

    let app = Router::new()
        .route("/api/corpora", get(get_corpora))
        .route("/api/facets", get(get_facets))
        .route("/api/records", get(get_records))
        .route("/api/records/{uuid}", get(get_record))
        .route("/api/submit", post(submit_capture))
        .route("/api/submissions", get(get_submissions))
        .layer(cors)
        .fallback_service(ServeDir::new(&static_dir))
        .with_state(state);

    let addr = "0.0.0.0:8080";
    tracing::info!("listening on http://{addr}");

    let listener = tokio::net::TcpListener::bind(addr).await?;
    axum::serve(listener, app).await?;

    Ok(())
}
