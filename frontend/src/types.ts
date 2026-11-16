export type RemoteMention = 'PRESENT' | 'NOT_MENTIONED' | 'UNKNOWN';
export type SortOrder = 'created_desc' | 'published_desc' | 'updated_desc';
export interface JobSummary {
  id: string;
  title: string | null;
  company_name: string | null;
  location_text: string | null;
  department: string | null;
  origin: 'manual' | 'ats';
  source_id: string | null;
  provider: string | null;
  board_token: string | null;
  external_job_id: string | null;
  source_url: string | null;
  remote_mention: RemoteMention;
  created_at: string;
  published_at: string | null;
  ingested_at: string;
  updated_at: string;
}
export interface JobDetail extends JobSummary {
  raw_text: string;
  description_text: string | null;
  source_updated_at: string | null;
}
export interface JobPage {
  items: JobSummary[];
  page: number;
  page_size: number;
  total: number;
  total_pages: number;
  source_options: { id: string; company_name: string; provider: string; board_token: string }[];
}
export interface JobCreated { job_id: string; task_id: string; status: string }
