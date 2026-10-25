// web/lib/types.ts - hinh dang JSON cua FastAPI (app/api/schemas.py).
export type PaperStatus = "processing" | "ready" | "failed";

export interface Paper {
  paper_id: string;
  title: string;
  num_chunks: number;
  has_pdf: boolean;
}

export interface Source {
  chunk_id: string;
  section: string;
  content_preview: string;
  text: string;
  page_num: number | null;
}

export interface AskResult {
  answer: string;
  thread_id: string;
  grade: "yes" | "no";
  rewrite_count: number;
  sources: Source[];
}

export interface StatusResult {
  paper_id: string;
  title: string;
  status: PaperStatus;
  num_chunks: number;
  has_pdf: boolean;
}

export interface UploadResult {
  paper_id: string;
  title: string;
  status: PaperStatus;
  num_chunks: number;
  message: string;
}
