use ath_core::corpus::Corpus;
use ath_core::dag::RecordDag;
use ath_core::filter::{group_records, Facets, GroupBy, RecordFilter};
use ath_core::model::{RecordType, Status};

fn test_corpus_path() -> std::path::PathBuf {
    std::path::PathBuf::from("/tmp/ath-test-corpus")
}

#[test]
fn load_test_corpus() {
    let corpus = Corpus::load(&test_corpus_path()).unwrap();

    // 4 sources + 1 document = 5 records
    assert_eq!(corpus.len(), 5);

    // Check a specific source record
    let uuid: uuid::Uuid = "f1a2b3c4-d5e6-4f7a-8b9c-0d1e2f3a4b5c".parse().unwrap();
    let record = corpus.get(&uuid).unwrap();
    assert_eq!(record.frontmatter.title, "AFM Delete Guide with Dyno Results");
    assert_eq!(record.frontmatter.record_type, RecordType::Source);
    assert_eq!(record.frontmatter.content_type, "forum_post");
    assert_eq!(record.frontmatter.status, Status::Normalized);
    assert!(record.body.contains("AFM Delete Procedure"));

    // Check extended fields are captured
    assert!(record.frontmatter.extended.contains_key("username"));
    assert!(record.frontmatter.extended.contains_key("reply_count"));

    // Check stub record with pending fields
    let stub_uuid: uuid::Uuid = "b2c3d4e5-f6a7-4b8c-9d0e-1f2a3b4c5d6e".parse().unwrap();
    let stub = corpus.get(&stub_uuid).unwrap();
    assert_eq!(stub.frontmatter.status, Status::Stub);
    assert_eq!(stub.frontmatter.credibility_tier.as_deref(), Some("pending"));
    assert!(stub.frontmatter.normalization_date.is_none());
}

#[test]
fn build_dag_from_corpus() {
    let corpus = Corpus::load(&test_corpus_path()).unwrap();
    let dag = RecordDag::build(&corpus.records);

    // The album document has one constituent (the metal archives source)
    let album_uuid: uuid::Uuid = "9c5f4d3e-6f7a-4b8c-0d1e-2f3a4b5c6d7e".parse().unwrap();
    let children = dag.children(&album_uuid);
    assert_eq!(children.len(), 1);

    let ma_uuid: uuid::Uuid = "a7b8c9d0-e1f2-4a3b-8c4d-5e6f7a8b9c0d".parse().unwrap();
    assert!(children.contains(&ma_uuid));

    // The metal archives source has the album as a parent
    let parents = dag.parents(&ma_uuid);
    assert_eq!(parents.len(), 1);
    assert!(parents.contains(&album_uuid));

    // Forum posts have no parents
    let forum_uuid: uuid::Uuid = "f1a2b3c4-d5e6-4f7a-8b9c-0d1e2f3a4b5c".parse().unwrap();
    assert!(dag.parents(&forum_uuid).is_empty());
}

#[test]
fn filter_records() {
    let corpus = Corpus::load(&test_corpus_path()).unwrap();

    // Filter by content type
    let mut filter = RecordFilter::default();
    filter.content_types.insert("forum_post".to_string());
    let matched: Vec<_> = corpus.records.values().filter(|r| filter.matches(r)).collect();
    assert_eq!(matched.len(), 2); // two forum posts

    // Text search
    let mut filter = RecordFilter::default();
    filter.search_text = "gorguts".to_string();
    let matched: Vec<_> = corpus.records.values().filter(|r| filter.matches(r)).collect();
    assert_eq!(matched.len(), 2); // MA source + album document (both tagged)

    // Filter by status
    let mut filter = RecordFilter::default();
    filter.statuses.insert(Status::Stub);
    let matched: Vec<_> = corpus.records.values().filter(|r| filter.matches(r)).collect();
    assert_eq!(matched.len(), 1); // the bank statement stub
}

#[test]
fn group_records_by_type() {
    let corpus = Corpus::load(&test_corpus_path()).unwrap();

    let groups = group_records(corpus.records.values(), GroupBy::ContentType);
    assert!(groups.contains_key("forum_post"));
    assert!(groups.contains_key("album"));
    assert!(groups.contains_key("metadata_page"));
    assert!(groups.contains_key("bank_statement"));
    assert_eq!(groups["forum_post"].len(), 2);
    assert_eq!(groups["album"].len(), 1);
}

#[test]
fn compute_facets() {
    let corpus = Corpus::load(&test_corpus_path()).unwrap();
    let facets = Facets::compute(corpus.records.values());

    assert!(facets.all_content_types.contains("forum_post"));
    assert!(facets.all_content_types.contains("album"));
    assert!(facets.all_tags.contains("gorguts"));
    assert!(facets.all_tags.contains("afm-delete"));
    assert!(facets.all_origin_names.contains("G8Board.com"));
    assert!(facets.all_origin_names.contains("Metal Archives"));
}
