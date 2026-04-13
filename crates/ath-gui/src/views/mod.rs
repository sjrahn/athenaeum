mod corpora;
mod detail;
mod records;
mod submit;

pub use corpora::corpora_window;
pub use detail::{detail_content, ArtifactRequest};
pub use records::records_window;
pub use records::RecordsAction;
pub use submit::submit_panel;
pub use submit::SubmitAction;
