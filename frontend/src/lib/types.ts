/** Wire types — mirror backend Pydantic schemas 1:1. Keep narrow. */

export interface User {
  id: string;
  email: string;
  display_name: string;
  created_at: string;
}

export interface Team {
  id: string;
  name: string;
  slug: string;
  owner_id: string;
  created_at: string;
}

export interface TeamMember {
  user_id: string;
  team_id: string;
  role: "owner" | "member";
  joined_at: string;
}

export interface ApiKey {
  id: string;
  name: string;
  prefix: string;
  last_used_at: string | null;
  created_at: string;
}

export interface ApiKeyWithToken extends ApiKey {
  /** Plaintext token — only returned on creation, never again. */
  token: string;
}

export interface Fix {
  id: string;
  team_id: string;
  project_id: string | null;
  created_by_id: string;
  content_hash: string;
  issue: string;
  resolution: string;
  error_excerpt: string | null;
  tags: string[] | null;
  notes: string | null;
  author: string | null;
  author_email: string | null;
  is_private: boolean;
  source_error_ids: string[] | null;
  applied_count: number;
  success_count: number;
  last_applied_at: string | null;
  memory_type: "fix" | "check" | "playbook" | "insight";
  created_at: string;
  updated_at: string;
}

export interface Paginated<T> {
  items: T[];
  total: number;
  limit: number;
  offset: number;
}

export interface PendingEntry {
  id: string;
  team_id: string;
  project_id: string | null;
  error_id: string;
  error_type: string;
  short_message: string;
  error_excerpt: string;
  tags: string;
  resource_address: string | null;
  error_code: string | null;
  status: "pending" | "superseded" | "resolved";
  worthiness: "memory_worthy" | "self_explanatory";
  kind: string | null;
  session_id: string | null;
  created_at: string;
  updated_at: string;
}
