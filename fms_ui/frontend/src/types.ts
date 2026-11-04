export interface SessionSummaryDTO {
  ref: string;
  harness: string;
  session_id: string;
  path: string;
  cwd: string;
  title: string;
  first_prompt: string;
  last_prompt: string;
  started: string | null;
  updated: string | null;
  branch: string;
  model: string;
  entrypoint: string;
  version: string;
  size_bytes: number;
  variants: string;
  archived: boolean;
}

export interface SessionListResponse {
  sessions: SessionSummaryDTO[];
  /** Non-deep list responses carry snapshot coordination metadata. */
  revision?: number;
  refreshing?: boolean;
}

export interface ProjectListResponse {
  projects: string[];
  revision: number;
  refreshing: boolean;
}

export interface HarnessRow {
  name: string;
  status: string;
  variants: string;
  store: string;
  aliases: string;
}

export interface HarnessListResponse {
  harnesses: HarnessRow[];
}

export interface ToolCallDTO {
  name: string;
  detail: string;
  timestamp: string | null;
}

export interface ExchangeDTO {
  user: string;
  timestamp: string | null;
  assistant: string[];
  tools: ToolCallDTO[];
}

export interface TodoDTO {
  status?: string;
  subject?: string;
  content?: string;
}

export interface EditedFileDTO {
  path?: string;
  count?: number;
}

export interface SessionDetailDTO extends SessionSummaryDTO {
  compact_summary: string;
  todos: TodoDTO[];
  turn_count: number;
  exchanges: ExchangeDTO[];
  edited_files: EditedFileDTO[];
  tool_counts: Record<string, number>;
  recent_tools: ToolCallDTO[];
  resume_argv: string[] | null;
}

export interface StatsRowDTO {
  harness: string;
  sessions: number;
  sessions_with_usage: number;
  tokens_input: number | null;
  tokens_output: number | null;
  tokens_cache_read: number | null;
  cost_usd: number | null;
}

export interface StatsResponseDTO {
  stats: StatsRowDTO[];
}

export interface UserPromptDTO {
  index: number;
  timestamp: string | null;
  text: string;
}

export interface PromptListingDTO {
  ref: string;
  harness: string;
  session_id: string;
  path: string;
  cwd: string;
  archived: boolean;
  total: number;
  offset: number;
  limit: number;
  order: string;
  returned: number;
  has_more: boolean;
  prompts: UserPromptDTO[];
}

export type SearchStatus = "ready" | "searching" | "refreshing" | "done" | "error";

export interface SearchFilters {
  query: string;
  harness: string;
  cwd: string;
  since: string;
  archived: boolean;
  deep: boolean;
}

export type DetailView = "empty" | "loading" | "content";

export type DetailTab = "overview" | "prompts" | "recent";
