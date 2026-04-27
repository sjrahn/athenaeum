# Content Types
Enumeration of the expected content sources and their respective metadata attributes

## Website

### News Article

### Forum Post

### Opinion / Editorial

### Blog Post

### Compendium Article (Wikipedia)


## Print (Physical/Electronic)

### Fiction Novel

### Non-fiction Novel

### Textbook

### Reference Manual

### Script / Screenplay

### Research Paper


## Audio-visual Media

### YouTube Video

### Podcast

### Television Show

### Feature Film

### Documentary


# Universal Document Metadata

    - Document ID (unique)
    - Title (text-50)
    - Description (text-150)
    - Content Value (enum)
    - Credibility (enum)
    - Normalization Date (date)
    - Normalization Model (text-50)
    - Normalization Confidence (number)
    - Sources Used (array)
        - Content Type (enum)
        - Capture Date (datetime)
        - Selective Content Type Metadata
    - Relations (array) - Move to file in sources?
    - Issues (array) - Move to file in sources?

# Universal Corpus Workflow

    1. Backlog Growth
        - Identify gaps
        - Add entries
    2. Backlog Grooming
        - Compare to captured and normalized for duplicates
        - Find re-ingest candidates
        - Reprioritization
    3. Ingestion (Acquisition)
        - Create batch, prioritized from backlog
        - Source files acquisition
        - Run deterministic stripping to create sidecars
        - Capture additional assets
        - Metadata assignment
        - Update backlog entry (orchestrator)
    4. Ingestion (Reconciliation)
        - Assign to subsection
        - If reconciled files exist
            - Move if content differs
            - Reset Metadata
            - Assets?
        - Move files
            - Source files to /sources/{subsection_slug}/{document_id}/
            - Assets to /manuscript/{subsection_slug}/assets/{document_id}/
        - Metadata assignment in source file sidecar frontmatter
        - Relation analyzer (in relations.toml)
        - Issue analyzer (in issues.toml)
        - Create stub normalized document (if not already exists)
            - Frontmatter assignment
        - Update backlog entry (orchestrator)
    5. Normalization
        - Concat sidecars
        - Processing
            - Light Context (<30K tokens>)
                - Read entirity into context
                - In-place format fixing and content adjustment into document
            - Medium Context (30K-100K tokens)
                - Chunked reading
                - In-place format fixing and content adjustment into document
            - Heavy Context (100K+ tokens)
                - Content sampling
                - Targeted format correction
        - Metadata adjustments
        - Update backlog entry (orchestrator)
    6. Corpus Status
        - Analyze Backlog status
            - Count priorities
            - Count subsections
        - Analyze Documents status
            - Count documents by section
            - Group normalization confidence
            - Count normalization model
        - Analyze repo structural integrity