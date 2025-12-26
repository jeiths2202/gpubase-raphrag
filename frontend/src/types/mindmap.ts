// Mindmap Types - API 응답과 호환되는 타입 정의

export type NodeType = 'root' | 'concept' | 'entity' | 'topic' | 'keyword';
export type RelationType = 'relates_to' | 'contains' | 'causes' | 'depends_on' | 'similar_to' | 'opposes' | 'part_of' | 'example_of';

export interface MindmapNode {
  id: string;
  label: string;
  type: NodeType;
  description?: string;
  importance: number;
  source_chunks?: string[];
  metadata?: Record<string, unknown>;
  x?: number;
  y?: number;
  color?: string;
  size?: number;
}

export interface MindmapEdge {
  id: string;
  source: string;
  target: string;
  relation: RelationType;
  label?: string;
  strength: number;
  bidirectional?: boolean;
}

export interface MindmapData {
  nodes: MindmapNode[];
  edges: MindmapEdge[];
  root_id?: string;
  metadata?: Record<string, unknown>;
}

export interface MindmapInfo {
  id: string;
  title: string;
  description?: string;
  document_ids: string[];
  node_count: number;
  edge_count: number;
  created_at?: string;
  updated_at?: string;
}

export interface MindmapFull extends MindmapInfo {
  data: MindmapData;
}

// Request types
export interface GenerateMindmapRequest {
  document_ids: string[];
  title?: string;
  max_nodes?: number;
  depth?: number;
  focus_topic?: string;
  language?: string;
}

export interface ExpandNodeRequest {
  node_id: string;
  depth?: number;
  max_children?: number;
}

export interface QueryNodeRequest {
  node_id: string;
  question?: string;
}

// Response types
export interface ApiResponse<T> {
  success: boolean;
  data: T;
  meta?: {
    request_id: string;
    timestamp?: string;
    processing_time_ms?: number;
  };
}

export interface GenerateMindmapResponse {
  mindmap: MindmapFull;
  message: string;
}

export interface ExpandNodeResponse {
  new_nodes: MindmapNode[];
  new_edges: MindmapEdge[];
  expanded_from: string;
}

export interface QueryNodeResponse {
  node_id: string;
  node_label: string;
  answer: string;
  related_concepts: string[];
  sources: Array<{
    chunk_id: string;
    doc_id: string;
    content: string;
  }>;
}

export interface NodeDetailResponse {
  node: MindmapNode;
  connected_nodes: MindmapNode[];
  edges: MindmapEdge[];
  source_content: Array<{
    chunk_id: string;
    doc_id: string;
    content: string;
  }>;
}
