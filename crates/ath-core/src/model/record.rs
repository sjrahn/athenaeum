use std::path::PathBuf;

use super::Frontmatter;

/// A fully loaded Athenaeum record: parsed frontmatter, markdown body, and
/// its filesystem location.
#[derive(Debug, Clone)]
pub struct Record {
    pub frontmatter: Frontmatter,
    pub body: String,
    pub file_path: PathBuf,
}
