use std::collections::HashSet;
use std::path::PathBuf;
use std::sync::Arc;
use std::time::Duration;

use notify::{EventKind, RecursiveMode, Watcher};

use ath_core::parse::parse_record;

/// Spawn a background thread that watches corpus directories for changes.
pub fn spawn_watcher(state: Arc<crate::ServerState>) {
    let dirs_to_watch = corpus_watch_dirs(&state);

    if dirs_to_watch.is_empty() {
        tracing::warn!("no corpus directories found to watch");
        return;
    }

    std::thread::spawn(move || {
        if let Err(e) = run_watcher(state, &dirs_to_watch) {
            tracing::error!(%e, "file watcher failed");
        }
    });
}

fn corpus_watch_dirs(state: &crate::ServerState) -> Vec<PathBuf> {
    let mut dirs = Vec::new();
    for (_name, path) in &state.corpus_paths {
        for sub in &["sources", "documents"] {
            let dir = path.join(sub);
            if dir.exists() {
                dirs.push(dir);
            }
        }
    }
    dirs
}

fn run_watcher(state: Arc<crate::ServerState>, dirs: &[PathBuf]) -> notify::Result<()> {
    let (tx, rx) = std::sync::mpsc::channel();

    let mut watcher = notify::recommended_watcher(tx)?;

    for dir in dirs {
        watcher.watch(dir, RecursiveMode::NonRecursive)?;
        tracing::info!(dir = %dir.display(), "watching for changes");
    }

    loop {
        // Collect events over a debounce window
        let mut changed_paths = HashSet::new();

        // Block until the first event arrives
        match rx.recv() {
            Ok(Ok(event)) => collect_paths(&event.kind, event.paths, &mut changed_paths),
            Ok(Err(e)) => {
                tracing::warn!(%e, "watch error");
                continue;
            }
            Err(_) => break, // channel closed
        }

        // Drain any additional events within the debounce window
        let deadline = Duration::from_millis(500);
        loop {
            match rx.recv_timeout(deadline) {
                Ok(Ok(event)) => collect_paths(&event.kind, event.paths, &mut changed_paths),
                Ok(Err(e)) => tracing::warn!(%e, "watch error"),
                Err(_) => break, // timeout — debounce window expired
            }
        }

        // Process the batch
        for path in changed_paths {
            if path.extension().is_some_and(|e| e == "md") {
                process_change(&state, &path);
            }
        }
    }

    Ok(())
}

fn collect_paths(kind: &EventKind, paths: Vec<PathBuf>, out: &mut HashSet<PathBuf>) {
    match kind {
        EventKind::Create(_) | EventKind::Modify(_) | EventKind::Remove(_) => {
            out.extend(paths);
        }
        _ => {}
    }
}

fn process_change(state: &crate::ServerState, path: &std::path::Path) {
    if path.exists() {
        // File created or modified — parse and upsert
        match parse_record(path) {
            Ok(record) => {
                let corpus_name = match resolve_corpus(state, path) {
                    Some(name) => name,
                    None => {
                        tracing::warn!(path = %path.display(), "cannot resolve corpus for path");
                        return;
                    }
                };

                let uuid = record.frontmatter.uuid;
                if let Err(e) = state.db.upsert_record(&corpus_name, &record) {
                    tracing::error!(%e, path = %path.display(), "failed to upsert record");
                    return;
                }

                // Update path index
                if let Ok(canonical) = path.canonicalize() {
                    state.path_index.lock().unwrap().insert(canonical, uuid);
                }

                tracing::info!(path = %path.display(), %uuid, "record updated");
            }
            Err(e) => {
                tracing::warn!(%e, path = %path.display(), "skipping unparseable file");
            }
        }
    } else {
        // File deleted — look up UUID from path index and remove
        let canonical = path.to_path_buf(); // can't canonicalize a deleted file
        let uuid = state.path_index.lock().unwrap().remove(&canonical);

        // Also try non-canonical path in case the index stored it differently
        let uuid = uuid.or_else(|| {
            let mut index = state.path_index.lock().unwrap();
            // Linear scan — rare operation (deletes)
            let key = index
                .iter()
                .find(|(k, _)| k.ends_with(path.file_name().unwrap_or_default()))
                .map(|(k, _)| k.clone());
            key.and_then(|k| index.remove(&k))
        });

        if let Some(uuid) = uuid {
            if let Err(e) = state.db.delete_record(uuid) {
                tracing::error!(%e, %uuid, "failed to delete record");
                return;
            }
            tracing::info!(%uuid, path = %path.display(), "record deleted");
        } else {
            tracing::debug!(path = %path.display(), "deleted file not in path index, ignoring");
        }
    }
}

fn resolve_corpus(state: &crate::ServerState, path: &std::path::Path) -> Option<String> {
    let canonical = path.canonicalize().ok()?;
    for (name, corpus_path) in &state.corpus_paths {
        if let Ok(corpus_canonical) = corpus_path.canonicalize()
            && canonical.starts_with(&corpus_canonical)
        {
            return Some(name.clone());
        }
    }
    None
}
