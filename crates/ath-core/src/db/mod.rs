use std::collections::HashMap;
use std::sync::Mutex;

use rusqlite::{params, Connection};
use uuid::Uuid;

use crate::api_types::*;
use crate::model::Record;

// Re-export API types for convenience
pub use crate::api_types::{
    CorpusInfo, FacetsResponse, QueryParams, QueryResult, RecordDetail, RecordSummary,
};

/// In-memory SQLite database for querying corpus records.
pub struct CorpusDb {
    conn: Mutex<Connection>,
}

impl CorpusDb {
    /// Create a new in-memory database with schema.
    pub fn open_memory() -> rusqlite::Result<Self> {
        let conn = Connection::open_in_memory()?;

        conn.execute_batch(
            "
            CREATE TABLE records (
                uuid TEXT PRIMARY KEY,
                corpus TEXT NOT NULL,
                title TEXT NOT NULL,
                description TEXT NOT NULL,
                record_type TEXT NOT NULL,
                content_type TEXT NOT NULL,
                status TEXT NOT NULL,
                credibility_tier TEXT,
                normalization_confidence REAL NOT NULL DEFAULT 0.0,
                origin_name TEXT,
                origin_url TEXT,
                capture_date TEXT,
                author TEXT,
                date_published TEXT,
                body TEXT NOT NULL DEFAULT '',
                record_json TEXT NOT NULL
            );

            CREATE TABLE record_tags (
                record_uuid TEXT NOT NULL,
                tag TEXT NOT NULL,
                PRIMARY KEY (record_uuid, tag)
            );

            CREATE TABLE constituents (
                parent_uuid TEXT NOT NULL,
                child_uuid TEXT NOT NULL,
                PRIMARY KEY (parent_uuid, child_uuid)
            );

            CREATE VIRTUAL TABLE records_fts USING fts5(
                title, description, body,
                content='records', content_rowid='rowid'
            );

            CREATE INDEX idx_records_corpus ON records(corpus);
            CREATE INDEX idx_records_content_type ON records(corpus, content_type);
            CREATE INDEX idx_records_status ON records(corpus, status);
            CREATE INDEX idx_records_title ON records(corpus, title COLLATE NOCASE);
            CREATE INDEX idx_record_tags_tag ON record_tags(tag);
            CREATE INDEX idx_constituents_child ON constituents(child_uuid);
            ",
        )?;

        Ok(CorpusDb {
            conn: Mutex::new(conn),
        })
    }

    /// Insert all records from a corpus into the database.
    pub fn insert_corpus(
        &self,
        corpus_name: &str,
        records: &HashMap<Uuid, Record>,
    ) -> rusqlite::Result<()> {
        let mut conn = self.conn.lock().unwrap();
        let tx = conn.transaction()?;

        {
            let mut insert_record = tx.prepare_cached(
                "INSERT OR REPLACE INTO records
                 (uuid, corpus, title, description, record_type, content_type, status,
                  credibility_tier, normalization_confidence, origin_name, origin_url,
                  capture_date, author, date_published, body, record_json)
                 VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7, ?8, ?9, ?10, ?11, ?12, ?13, ?14, ?15, ?16)",
            )?;

            let mut insert_tag = tx.prepare_cached(
                "INSERT OR IGNORE INTO record_tags (record_uuid, tag) VALUES (?1, ?2)",
            )?;

            let mut insert_constituent = tx.prepare_cached(
                "INSERT OR IGNORE INTO constituents (parent_uuid, child_uuid) VALUES (?1, ?2)",
            )?;

            for record in records.values() {
                let fm = &record.frontmatter;
                let uuid_str = fm.uuid.to_string();
                let record_json = serde_json::to_string(record).unwrap_or_default();

                insert_record.execute(params![
                    uuid_str,
                    corpus_name,
                    fm.title,
                    fm.description,
                    fm.record_type.to_string(),
                    fm.content_type,
                    fm.status.to_string(),
                    fm.credibility_tier,
                    fm.normalization_confidence,
                    fm.origin_name,
                    fm.origin_url,
                    fm.capture_date.map(|d| d.to_string()),
                    fm.author,
                    fm.date_published.map(|d| d.to_string()),
                    record.body,
                    record_json,
                ])?;

                for tag in &fm.tags {
                    insert_tag.execute(params![uuid_str, tag])?;
                }

                if let Some(constituents) = &fm.constituents {
                    for child in constituents {
                        insert_constituent.execute(params![uuid_str, child.to_string()])?;
                    }
                }
            }
        }

        // Populate FTS index
        tx.execute_batch(
            "INSERT INTO records_fts(rowid, title, description, body)
             SELECT rowid, title, description, body FROM records",
        )?;

        tx.commit()
    }

    /// List all corpora with record counts.
    pub fn list_corpora(&self) -> rusqlite::Result<Vec<CorpusInfo>> {
        let conn = self.conn.lock().unwrap();
        let mut stmt = conn.prepare(
            "SELECT corpus, COUNT(*) FROM records GROUP BY corpus ORDER BY corpus",
        )?;

        let rows = stmt.query_map([], |row| {
            Ok(CorpusInfo {
                name: row.get(0)?,
                record_count: row.get(1)?,
            })
        })?;

        rows.collect()
    }

    /// Get distinct facet values for a corpus.
    pub fn facets(&self, corpus: &str) -> rusqlite::Result<FacetsResponse> {
        let conn = self.conn.lock().unwrap();

        let content_types = query_distinct(
            &conn,
            "SELECT DISTINCT content_type FROM records WHERE corpus = ?1 ORDER BY content_type",
            corpus,
        )?;

        let statuses = query_distinct(
            &conn,
            "SELECT DISTINCT status FROM records WHERE corpus = ?1 ORDER BY status",
            corpus,
        )?;

        let tags = query_distinct(
            &conn,
            "SELECT DISTINCT tag FROM record_tags rt
             JOIN records r ON r.uuid = rt.record_uuid
             WHERE r.corpus = ?1 ORDER BY tag",
            corpus,
        )?;

        let origin_names = query_distinct(
            &conn,
            "SELECT DISTINCT origin_name FROM records
             WHERE corpus = ?1 AND origin_name IS NOT NULL ORDER BY origin_name",
            corpus,
        )?;

        let credibility_tiers = query_distinct(
            &conn,
            "SELECT DISTINCT credibility_tier FROM records
             WHERE corpus = ?1 AND credibility_tier IS NOT NULL ORDER BY credibility_tier",
            corpus,
        )?;

        Ok(FacetsResponse {
            content_types,
            statuses,
            tags,
            origin_names,
            credibility_tiers,
        })
    }

    /// Query records with filtering, sorting, and pagination.
    pub fn query_records(&self, params: &QueryParams) -> rusqlite::Result<QueryResult> {
        let conn = self.conn.lock().unwrap();

        let mut conditions = vec!["r.corpus = :corpus".to_string()];
        let mut bind_values: Vec<(String, Box<dyn rusqlite::types::ToSql>)> = vec![
            (":corpus".to_string(), Box::new(params.corpus.clone())),
        ];

        // Full-text search
        let use_fts = !params.q.is_empty();
        let mut from_clause = if use_fts {
            conditions.push("r.rowid IN (SELECT rowid FROM records_fts WHERE records_fts MATCH :query)".to_string());
            bind_values.push((":query".to_string(), Box::new(fts5_escape(&params.q))));
            "records r".to_string()
        } else {
            "records r".to_string()
        };

        if let Some(ct) = &params.content_type {
            conditions.push("r.content_type = :content_type".to_string());
            bind_values.push((":content_type".to_string(), Box::new(ct.clone())));
        }

        if let Some(st) = &params.status {
            conditions.push("r.status = :status".to_string());
            bind_values.push((":status".to_string(), Box::new(st.clone())));
        }

        if let Some(tag) = &params.tag {
            from_clause.push_str(
                " JOIN record_tags rt ON rt.record_uuid = r.uuid"
            );
            conditions.push("rt.tag = :tag".to_string());
            bind_values.push((":tag".to_string(), Box::new(tag.clone())));
        }

        if let Some(on) = &params.origin_name {
            conditions.push("r.origin_name = :origin_name".to_string());
            bind_values.push((":origin_name".to_string(), Box::new(on.clone())));
        }

        if let Some(ct) = &params.credibility_tier {
            conditions.push("r.credibility_tier = :credibility_tier".to_string());
            bind_values.push((":credibility_tier".to_string(), Box::new(ct.clone())));
        }

        if let Some(rt) = &params.record_type {
            conditions.push("r.record_type = :record_type".to_string());
            bind_values.push((":record_type".to_string(), Box::new(rt.clone())));
        }

        let where_clause = conditions.join(" AND ");

        let order_clause = match params.sort.as_str() {
            "title_desc" => "r.title COLLATE NOCASE DESC",
            "status_asc" => "r.status ASC, r.title COLLATE NOCASE ASC",
            "newest_first" => "r.capture_date DESC, r.title COLLATE NOCASE ASC",
            _ => "r.title COLLATE NOCASE ASC",
        };

        // Count query
        let count_sql = format!("SELECT COUNT(DISTINCT r.uuid) FROM {from_clause} WHERE {where_clause}");
        let mut count_stmt = conn.prepare(&count_sql)?;
        let param_refs: Vec<(&str, &dyn rusqlite::types::ToSql)> = bind_values
            .iter()
            .map(|(k, v)| (k.as_str(), v.as_ref() as &dyn rusqlite::types::ToSql))
            .collect();
        let total: u64 = count_stmt.query_row(param_refs.as_slice(), |row| row.get(0))?;

        // Data query
        let data_sql = format!(
            "SELECT DISTINCT r.uuid, r.title, r.status, r.content_type, r.record_type
             FROM {from_clause}
             WHERE {where_clause}
             ORDER BY {order_clause}
             LIMIT :limit OFFSET :offset"
        );

        let mut all_params = bind_values;
        all_params.push((":limit".to_string(), Box::new(params.limit as i64)));
        all_params.push((":offset".to_string(), Box::new(params.offset as i64)));

        let param_refs: Vec<(&str, &dyn rusqlite::types::ToSql)> = all_params
            .iter()
            .map(|(k, v)| (k.as_str(), v.as_ref() as &dyn rusqlite::types::ToSql))
            .collect();

        let mut data_stmt = conn.prepare(&data_sql)?;
        let rows = data_stmt.query_map(param_refs.as_slice(), |row| {
            let uuid_str: String = row.get(0)?;
            Ok((uuid_str, row.get(1)?, row.get(2)?, row.get(3)?, row.get(4)?))
        })?;

        let mut records = Vec::new();
        for row in rows {
            let (uuid_str, title, status, content_type, record_type): (String, String, String, String, String) = row?;

            // Fetch tags for this record
            let tags = self.get_tags_inner(&conn, &uuid_str)?;

            records.push(RecordSummary {
                uuid: uuid_str.parse().unwrap_or_default(),
                title,
                status,
                content_type,
                record_type,
                tags,
            });
        }

        Ok(QueryResult { total, records })
    }

    /// Get a full record by UUID.
    pub fn get_record(&self, uuid: Uuid) -> rusqlite::Result<Option<RecordDetail>> {
        let conn = self.conn.lock().unwrap();

        let uuid_str = uuid.to_string();

        let record_json: Option<String> = conn
            .prepare("SELECT record_json FROM records WHERE uuid = ?1")?
            .query_row(params![uuid_str], |row| row.get(0))
            .ok();

        let Some(json) = record_json else {
            return Ok(None);
        };

        let record: Record = match serde_json::from_str(&json) {
            Ok(r) => r,
            Err(e) => {
                tracing::error!(%e, "failed to deserialize record from db");
                return Ok(None);
            }
        };

        // Get parent documents (records that list this as a constituent)
        let parents = self.get_parents_inner(&conn, &uuid_str)?;

        // Get children (constituents of this record)
        let children = self.get_children_inner(&conn, &uuid_str)?;

        Ok(Some(RecordDetail {
            record,
            parents,
            children,
        }))
    }

    fn get_tags_inner(&self, conn: &Connection, uuid_str: &str) -> rusqlite::Result<Vec<String>> {
        let mut stmt = conn.prepare_cached(
            "SELECT tag FROM record_tags WHERE record_uuid = ?1 ORDER BY tag",
        )?;
        let rows = stmt.query_map(params![uuid_str], |row| row.get(0))?;
        rows.collect()
    }

    fn get_parents_inner(
        &self,
        conn: &Connection,
        uuid_str: &str,
    ) -> rusqlite::Result<Vec<RecordSummary>> {
        let mut stmt = conn.prepare_cached(
            "SELECT r.uuid, r.title, r.status, r.content_type, r.record_type
             FROM records r
             JOIN constituents c ON c.parent_uuid = r.uuid
             WHERE c.child_uuid = ?1",
        )?;

        let rows = stmt.query_map(params![uuid_str], |row| {
            Ok((row.get(0)?, row.get(1)?, row.get(2)?, row.get(3)?, row.get(4)?))
        })?;

        let mut result = Vec::new();
        for row in rows {
            let (uuid_s, title, status, content_type, record_type): (String, String, String, String, String) = row?;
            let tags = self.get_tags_inner(conn, &uuid_s)?;
            result.push(RecordSummary {
                uuid: uuid_s.parse().unwrap_or_default(),
                title,
                status,
                content_type,
                record_type,
                tags,
            });
        }

        Ok(result)
    }

    fn get_children_inner(
        &self,
        conn: &Connection,
        uuid_str: &str,
    ) -> rusqlite::Result<Vec<RecordSummary>> {
        let mut stmt = conn.prepare_cached(
            "SELECT r.uuid, r.title, r.status, r.content_type, r.record_type
             FROM records r
             JOIN constituents c ON c.child_uuid = r.uuid
             WHERE c.parent_uuid = ?1",
        )?;

        let rows = stmt.query_map(params![uuid_str], |row| {
            Ok((row.get(0)?, row.get(1)?, row.get(2)?, row.get(3)?, row.get(4)?))
        })?;

        let mut result = Vec::new();
        for row in rows {
            let (uuid_s, title, status, content_type, record_type): (String, String, String, String, String) = row?;
            let tags = self.get_tags_inner(conn, &uuid_s)?;
            result.push(RecordSummary {
                uuid: uuid_s.parse().unwrap_or_default(),
                title,
                status,
                content_type,
                record_type,
                tags,
            });
        }

        Ok(result)
    }
}

/// Escape user input for FTS5 queries.
/// Wraps each word in double quotes to prevent syntax errors from special characters.
fn fts5_escape(query: &str) -> String {
    query
        .split_whitespace()
        .map(|word| format!("\"{}\"", word.replace('"', "\"\"")))
        .collect::<Vec<_>>()
        .join(" ")
}

fn query_distinct(
    conn: &Connection,
    sql: &str,
    corpus: &str,
) -> rusqlite::Result<Vec<String>> {
    let mut stmt = conn.prepare(sql)?;
    let rows = stmt.query_map(params![corpus], |row| row.get(0))?;
    rows.collect()
}
