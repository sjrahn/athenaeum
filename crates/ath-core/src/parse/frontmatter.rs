use std::path::Path;

use serde_yaml_ng::Value;

use crate::error::{Error, Result};
use crate::model::{Frontmatter, Record};

/// Rewrite v8-era `relations: [{type, target}, ...]` into the v9 flat
/// `part_of` / `same_as` lists. Drops deprecated relation types with a warning.
///
/// Runs on the raw YAML mapping before struct deserialization so no legacy
/// field leaks into `Frontmatter.extended`.
fn migrate_legacy_relations(value: &mut Value, path: &Path) {
    let Value::Mapping(map) = value else { return };
    let Some(relations_value) = map.remove("relations") else {
        return;
    };
    let Value::Sequence(entries) = relations_value else {
        tracing::warn!(path = %path.display(), "relations field is not a sequence, dropping");
        return;
    };

    let mut part_of: Vec<Value> = Vec::new();
    let mut same_as: Vec<Value> = Vec::new();

    for entry in entries {
        let Value::Mapping(entry_map) = entry else {
            continue;
        };
        let rel_type = entry_map.get("type").and_then(Value::as_str).unwrap_or("");
        let target = entry_map.get("target").cloned();

        match rel_type {
            "part_of" => {
                if let Some(t) = target {
                    part_of.push(t);
                }
            }
            "same_as" => {
                if let Some(t) = target {
                    same_as.push(t);
                }
            }
            other => {
                tracing::warn!(
                    path = %path.display(),
                    relation_type = other,
                    "dropping deprecated v8 relation type"
                );
            }
        }
    }

    if !part_of.is_empty() {
        merge_uuid_list(map, "part_of", part_of);
    }
    if !same_as.is_empty() {
        merge_uuid_list(map, "same_as", same_as);
    }
}

fn merge_uuid_list(map: &mut serde_yaml_ng::Mapping, key: &str, mut extracted: Vec<Value>) {
    let key_val = Value::String(key.to_string());
    if let Some(existing) = map.remove(key) {
        if let Value::Sequence(mut seq) = existing {
            seq.append(&mut extracted);
            map.insert(key_val, Value::Sequence(seq));
            return;
        }
    }
    map.insert(key_val, Value::Sequence(extracted));
}

/// Split a markdown file's content into YAML frontmatter and body.
///
/// Expects the file to start with `---\n`, followed by YAML, then `---\n`
/// (or `---` at EOF), then the body.
fn split_frontmatter(content: &str) -> Option<(&str, &str)> {
    let content = content.strip_prefix("---\n").or_else(|| content.strip_prefix("---\r\n"))?;

    // Find the closing ---
    if let Some(pos) = content.find("\n---\n") {
        let yaml = &content[..pos];
        let body = &content[pos + 5..]; // skip "\n---\n"
        Some((yaml, body))
    } else if let Some(pos) = content.find("\n---\r\n") {
        let yaml = &content[..pos];
        let body = &content[pos + 6..];
        Some((yaml, body))
    } else if content.ends_with("\n---") || content.ends_with("\n---\n") {
        let pos = content.rfind("\n---").unwrap();
        let yaml = &content[..pos];
        Some((yaml, ""))
    } else {
        // No closing delimiter found — treat entire content as YAML with empty body
        Some((content, ""))
    }
}

/// Parse a single record file from disk.
pub fn parse_record(path: &Path) -> Result<Record> {
    let content = std::fs::read_to_string(path).map_err(|e| Error::FileRead {
        path: path.to_owned(),
        source: e,
    })?;

    let (yaml_str, body) = split_frontmatter(&content).ok_or_else(|| Error::FrontmatterParse {
        path: path.to_owned(),
        detail: "file does not start with '---'".to_string(),
    })?;

    let mut yaml_value: Value =
        serde_yaml_ng::from_str(yaml_str).map_err(|e| Error::YamlDeserialize {
            path: path.to_owned(),
            source: e,
        })?;

    migrate_legacy_relations(&mut yaml_value, path);

    let frontmatter: Frontmatter =
        serde_yaml_ng::from_value(yaml_value).map_err(|e| Error::YamlDeserialize {
            path: path.to_owned(),
            source: e,
        })?;

    Ok(Record {
        frontmatter,
        body: body.to_owned(),
        file_path: path.to_owned(),
    })
}

/// Serialize a record back to its markdown file format.
pub fn serialize_record(record: &Record) -> Result<String> {
    let yaml = serde_yaml_ng::to_string(&record.frontmatter)?;
    Ok(format!("---\n{yaml}---\n{}", record.body))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn split_basic_frontmatter() {
        let content = "---\ntitle: Hello\n---\nBody text here.";
        let (yaml, body) = split_frontmatter(content).unwrap();
        assert_eq!(yaml, "title: Hello");
        assert_eq!(body, "Body text here.");
    }

    #[test]
    fn split_empty_body() {
        let content = "---\ntitle: Hello\n---\n";
        let (yaml, body) = split_frontmatter(content).unwrap();
        assert_eq!(yaml, "title: Hello");
        assert_eq!(body, "");
    }

    #[test]
    fn split_no_opening_delimiter() {
        let content = "Just regular text.";
        assert!(split_frontmatter(content).is_none());
    }

    #[test]
    fn parse_source_record() {
        let yaml = r#"---
uuid: "f1a2b3c4-d5e6-4f7a-8b9c-0d1e2f3a4b5c"
title: "AFM Delete Guide with Dyno Results"
description: "Detailed walkthrough of AFM/DoD delete on an L76 6.0L."
record_type: source
content_type: forum_post
status: normalized
tags: ["afm-delete", "l76", "engine"]
origin_url: "https://www.g8board.com/threads/afm-delete-guide.56789/"
origin_name: "G8Board.com"
capture_date: 2026-03-01
artifact_refs:
  - ref: "artifacts://thread.html"
    sha256: "e3b0c44298fc1c149afbf4c8996fb924"
date_published: 2023-08-15
credibility_tier: community_validated
normalization_confidence: 0.92
normalization_model: "claude-sonnet-4-5-20250514"
normalization_date: 2026-03-01
conversion_method: "g8board-scraper"
conversion_tool: "scrape_thread.py v0.6"
conversion_date: 2026-03-01
username: "LS3SwapKing"
thread_url: "https://www.g8board.com/threads/afm-delete-guide.56789/"
reply_count: 47
---
## AFM Delete Procedure

The Active Fuel Management (AFM) system on the L76 can be fully deleted...
"#;
        let dir = std::env::temp_dir().join("ath-core-test-source");
        std::fs::create_dir_all(&dir).unwrap();
        let path = dir.join("f1a2b3c4-d5e6-4f7a-8b9c-0d1e2f3a4b5c.md");
        std::fs::write(&path, yaml).unwrap();

        let record = parse_record(&path).unwrap();
        assert_eq!(record.frontmatter.title, "AFM Delete Guide with Dyno Results");
        assert_eq!(record.frontmatter.content_type, "forum_post");
        assert_eq!(record.frontmatter.tags, vec!["afm-delete", "l76", "engine"]);
        assert_eq!(record.frontmatter.artifact_refs.len(), 1);
        assert_eq!(record.frontmatter.artifact_refs[0].uri, "artifacts://thread.html");
        // Extended fields
        assert_eq!(
            record.frontmatter.extended.get("username"),
            Some(&serde_yaml_ng::Value::String("LS3SwapKing".to_string()))
        );
        assert_eq!(
            record.frontmatter.extended.get("reply_count"),
            Some(&serde_yaml_ng::Value::Number(47.into()))
        );
        assert!(record.body.contains("AFM Delete Procedure"));

        std::fs::remove_dir_all(&dir).ok();
    }

    #[test]
    fn parse_document_record() {
        let yaml = r#"---
uuid: "9c5f4d3e-6f7a-4b8c-0d1e-2f3a4b5c6d7e"
title: "Obscura"
description: "Gorguts' third studio album (1998)."
record_type: document
content_type: album
status: normalized
tags: ["gorguts", "death-metal"]
constituents:
  - "a7b8c9d0-e1f2-4a3b-8c4d-5e6f7a8b9c0d"
  - "e1f2a3b4-c5d6-4e7f-8a9b-0c1d2e3f4a5b"
merge_rationale: "All records related to the Gorguts album Obscura"
credibility_tier: authoritative
normalization_confidence: 0.90
normalization_model: "claude-sonnet-4-5-20250514"
normalization_date: 2026-03-17
artist_name: "Gorguts"
release_date: 1998
label: "Olympic Recordings"
track_count: 8
genre: ["technical death metal", "avant-garde metal"]
---
## Obscura (1998)

Gorguts' third album represents a radical departure.
"#;
        let dir = std::env::temp_dir().join("ath-core-test-doc");
        std::fs::create_dir_all(&dir).unwrap();
        let path = dir.join("9c5f4d3e-6f7a-4b8c-0d1e-2f3a4b5c6d7e.md");
        std::fs::write(&path, yaml).unwrap();

        let record = parse_record(&path).unwrap();
        assert_eq!(record.frontmatter.title, "Obscura");
        assert_eq!(record.frontmatter.content_type, "album");
        let constituents = record.frontmatter.constituents.as_ref().unwrap();
        assert_eq!(constituents.len(), 2);
        assert_eq!(
            record.frontmatter.extended.get("artist_name"),
            Some(&serde_yaml_ng::Value::String("Gorguts".to_string()))
        );
        assert!(record.body.contains("radical departure"));

        std::fs::remove_dir_all(&dir).ok();
    }

    #[test]
    fn parse_stub_with_pending_fields() {
        let yaml = r#"---
uuid: "a1b2c3d4-e5f6-4a7b-8c9d-0e1f2a3b4c5d"
title: "TODO"
description: ""
record_type: source
content_type: bank_statement
status: stub
origin_name: "RBC"
capture_date: 2026-02-03
artifact_refs:
  - ref: "artifacts://statement.pdf"
    sha256: "a1b2c3d4e5f6"
tags: []
credibility_tier: pending
normalization_confidence: 0.0
normalization_model: "pending"
normalization_date: pending
---
"#;
        let dir = std::env::temp_dir().join("ath-core-test-stub");
        std::fs::create_dir_all(&dir).unwrap();
        let path = dir.join("a1b2c3d4-e5f6-4a7b-8c9d-0e1f2a3b4c5d.md");
        std::fs::write(&path, yaml).unwrap();

        let record = parse_record(&path).unwrap();
        assert_eq!(record.frontmatter.credibility_tier.as_deref(), Some("pending"));
        assert!(record.frontmatter.normalization_date.is_none());
        assert_eq!(
            record.frontmatter.normalization_model.as_deref(),
            Some("pending")
        );

        std::fs::remove_dir_all(&dir).ok();
    }

    #[test]
    fn round_trip_serialization() {
        let yaml = r#"---
uuid: "f1a2b3c4-d5e6-4f7a-8b9c-0d1e2f3a4b5c"
title: "Test Record"
description: "A test."
record_type: source
content_type: web_article
status: draft
origin_name: "Example.com"
capture_date: 2026-01-15
artifact_refs:
  - ref: "artifacts://page.html"
    sha256: "abc123"
credibility_tier: anecdotal
normalization_confidence: 0.85
normalization_model: "claude-sonnet-4-5-20250514"
normalization_date: 2026-01-15
article_url: "https://example.com/article"
---
## Test Article

Some body content here.
"#;
        let dir = std::env::temp_dir().join("ath-core-test-roundtrip");
        std::fs::create_dir_all(&dir).unwrap();
        let path = dir.join("f1a2b3c4-d5e6-4f7a-8b9c-0d1e2f3a4b5c.md");
        std::fs::write(&path, yaml).unwrap();

        let record = parse_record(&path).unwrap();
        let serialized = serialize_record(&record).unwrap();

        // Re-parse the serialized version
        let reparsed: Frontmatter = {
            let (yaml_str, _) = split_frontmatter(&serialized).unwrap();
            serde_yaml_ng::from_str(yaml_str).unwrap()
        };

        assert_eq!(reparsed.uuid, record.frontmatter.uuid);
        assert_eq!(reparsed.title, record.frontmatter.title);
        assert_eq!(reparsed.content_type, record.frontmatter.content_type);
        assert_eq!(
            reparsed.extended.get("article_url"),
            record.frontmatter.extended.get("article_url")
        );

        std::fs::remove_dir_all(&dir).ok();
    }
}
