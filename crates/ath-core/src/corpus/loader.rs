use std::collections::HashMap;
use std::path::{Path, PathBuf};

use uuid::Uuid;

use crate::error::{Error, Result};
use crate::model::Record;
use crate::parse::parse_record;

/// A loaded corpus — all records in memory with their metadata.
pub struct Corpus {
    pub records: HashMap<Uuid, Record>,
    pub root_path: PathBuf,
}

impl Corpus {
    /// Load all records from a corpus directory.
    ///
    /// Scans `sources/` and `documents/` for `.md` files, parses each one,
    /// and collects them into a HashMap keyed by UUID.
    /// Unparseable files are logged and skipped.
    pub fn load(root: &Path) -> Result<Self> {
        if !root.exists() {
            return Err(Error::CorpusNotFound(root.to_owned()));
        }

        let mut records = HashMap::new();

        for dir_name in &["sources", "documents"] {
            let dir_path = root.join(dir_name);
            if !dir_path.exists() {
                continue;
            }

            let entries = std::fs::read_dir(&dir_path).map_err(|e| Error::FileRead {
                path: dir_path.clone(),
                source: e,
            })?;

            for entry in entries {
                let entry = entry.map_err(|e| Error::FileRead {
                    path: dir_path.clone(),
                    source: e,
                })?;

                let path = entry.path();
                if path.extension().is_some_and(|e| e == "md") {
                    match parse_record(&path) {
                        Ok(record) => {
                            records.insert(record.frontmatter.uuid, record);
                        }
                        Err(e) => {
                            tracing::warn!(?path, %e, "skipping unparseable record");
                        }
                    }
                }
            }
        }

        Ok(Corpus {
            records,
            root_path: root.to_owned(),
        })
    }

    /// Reload a single record from disk by its file path.
    pub fn reload_record(&mut self, path: &Path) -> Result<()> {
        let record = parse_record(path)?;
        self.records.insert(record.frontmatter.uuid, record);
        Ok(())
    }

    /// Remove a record by UUID.
    pub fn remove_record(&mut self, uuid: &Uuid) -> Option<Record> {
        self.records.remove(uuid)
    }

    /// Get a record by UUID.
    pub fn get(&self, uuid: &Uuid) -> Option<&Record> {
        self.records.get(uuid)
    }

    /// Number of records in the corpus.
    pub fn len(&self) -> usize {
        self.records.len()
    }

    /// Whether the corpus is empty.
    pub fn is_empty(&self) -> bool {
        self.records.is_empty()
    }

    /// Create a corpus from pre-loaded records (used by web/WASM target).
    pub fn from_records(records: HashMap<Uuid, Record>) -> Self {
        Corpus {
            records,
            root_path: PathBuf::new(),
        }
    }
}
