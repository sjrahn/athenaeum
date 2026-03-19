use crate::error::{Error, Result};
use crate::model::Record;
use crate::parse::serialize_record;

/// Write a record back to its file path atomically.
///
/// Writes to a temporary file first, then renames to the target path.
pub fn write_record(record: &Record) -> Result<()> {
    let content = serialize_record(record)?;
    let tmp_path = record.file_path.with_extension("md.tmp");

    std::fs::write(&tmp_path, &content).map_err(|e| Error::FileWrite {
        path: tmp_path.clone(),
        source: e,
    })?;

    std::fs::rename(&tmp_path, &record.file_path).map_err(|e| Error::FileWrite {
        path: record.file_path.clone(),
        source: e,
    })?;

    Ok(())
}
