use std::path::PathBuf;

#[derive(Debug, thiserror::Error)]
pub enum Error {
    #[error("failed to read file {path}: {source}")]
    FileRead {
        path: PathBuf,
        source: std::io::Error,
    },

    #[error("failed to write file {path}: {source}")]
    FileWrite {
        path: PathBuf,
        source: std::io::Error,
    },

    #[error("invalid frontmatter in {path}: {detail}")]
    FrontmatterParse { path: PathBuf, detail: String },

    #[error("YAML deserialization error in {path}: {source}")]
    YamlDeserialize {
        path: PathBuf,
        source: serde_yaml_ng::Error,
    },

    #[error("YAML serialization error: {0}")]
    YamlSerialize(#[from] serde_yaml_ng::Error),

    #[error("corpus directory not found: {0}")]
    CorpusNotFound(PathBuf),

    #[error("schema parse error in {path}: {detail}")]
    SchemaParse { path: PathBuf, detail: String },
}

pub type Result<T> = std::result::Result<T, Error>;
