use std::collections::HashMap;

use petgraph::stable_graph::{NodeIndex, StableGraph};
use uuid::Uuid;

use crate::model::Record;

/// The merge DAG — records connected by constituent relationships.
pub struct RecordDag {
    pub graph: StableGraph<Uuid, ()>,
    pub node_map: HashMap<Uuid, NodeIndex>,
}

impl RecordDag {
    /// Build the DAG from a set of records.
    ///
    /// Creates a node for every record and an edge from each document
    /// to its constituents.
    pub fn build(records: &HashMap<Uuid, Record>) -> Self {
        let mut graph = StableGraph::new();
        let mut node_map = HashMap::new();

        // Create nodes
        for &uuid in records.keys() {
            let idx = graph.add_node(uuid);
            node_map.insert(uuid, idx);
        }

        // Create edges: document -> constituent
        for record in records.values() {
            if let Some(constituents) = &record.frontmatter.constituents {
                if let Some(&parent_idx) = node_map.get(&record.frontmatter.uuid) {
                    for child_uuid in constituents {
                        if let Some(&child_idx) = node_map.get(child_uuid) {
                            graph.add_edge(parent_idx, child_idx, ());
                        }
                    }
                }
            }
        }

        RecordDag { graph, node_map }
    }

    /// Direct children (constituents) of a record.
    pub fn children(&self, uuid: &Uuid) -> Vec<Uuid> {
        let Some(&idx) = self.node_map.get(uuid) else {
            return vec![];
        };
        self.graph
            .neighbors_directed(idx, petgraph::Direction::Outgoing)
            .filter_map(|n| self.graph.node_weight(n).copied())
            .collect()
    }

    /// Direct parents (documents that include this record as a constituent).
    pub fn parents(&self, uuid: &Uuid) -> Vec<Uuid> {
        let Some(&idx) = self.node_map.get(uuid) else {
            return vec![];
        };
        self.graph
            .neighbors_directed(idx, petgraph::Direction::Incoming)
            .filter_map(|n| self.graph.node_weight(n).copied())
            .collect()
    }
}
