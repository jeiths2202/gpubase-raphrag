export interface ProgressSnapshot {
  status: string;
  progress: number;
  currentStep: string;
  timestamp: string;
  issuesFound: number;
  issuesCrawled: number;
  relatedCount?: number;
}

export interface CompletionStats {
  totalIssues: number;
  successfulIssues: number;
  duration: number;
  outcome: 'success' | 'partial' | 'failed';
  relatedIssues?: number;
  attachments?: number;
  failedIssues?: number;
  progressSnapshot?: ProgressSnapshot;
}
