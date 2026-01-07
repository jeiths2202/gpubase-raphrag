/**
 * IMS Crawler Mock API Handlers
 *
 * MSW handlers for IMS crawler endpoints
 */

import { http, HttpResponse, delay } from 'msw';

// Types
export type CrawlerStatus = 'idle' | 'running' | 'paused' | 'completed' | 'failed';
export type JobStatus = 'pending' | 'running' | 'completed' | 'failed' | 'paused';
export type LogLevel = 'info' | 'warning' | 'error' | 'debug';

export interface CrawlerState {
  status: CrawlerStatus;
  progress: number;
  currentUrl: string | null;
  startTime: string | null;
  estimatedRemaining: number | null;
}

export interface CrawlJob {
  id: string;
  name: string;
  url: string;
  description: string;
  status: JobStatus;
  documentCount: number;
  createdAt: string;
  updatedAt: string;
  progress: number;
}

export interface CrawlStats {
  totalDocuments: number;
  newDocuments: number;
  updatedDocuments: number;
  failedDocuments: number;
  lastUpdated: string;
}

export interface CrawlerSettings {
  depth: number;
  interval: number;
  timeout: number;
  documentTypes: string[];
}

export interface LogEntry {
  id: string;
  timestamp: string;
  level: LogLevel;
  message: string;
  source: string;
}

// Mock state
let crawlerState: CrawlerState = {
  status: 'idle',
  progress: 0,
  currentUrl: null,
  startTime: null,
  estimatedRemaining: null,
};

let crawlerSettings: CrawlerSettings = {
  depth: 3,
  interval: 2,
  timeout: 30,
  documentTypes: ['html', 'pdf', 'doc', 'docx', 'md', 'txt'],
};

// Mock jobs data
const MOCK_JOBS: CrawlJob[] = [
  {
    id: 'job-001',
    name: 'Documentation Portal',
    url: 'https://docs.example.com',
    description: 'Main documentation site crawl',
    status: 'completed',
    documentCount: 156,
    createdAt: '2024-01-15T09:00:00Z',
    updatedAt: '2024-01-15T12:30:00Z',
    progress: 100,
  },
  {
    id: 'job-002',
    name: 'API Reference',
    url: 'https://api.example.com/docs',
    description: 'API documentation and reference',
    status: 'running',
    documentCount: 45,
    createdAt: '2024-01-18T14:00:00Z',
    updatedAt: '2024-01-18T14:45:00Z',
    progress: 67,
  },
  {
    id: 'job-003',
    name: 'Knowledge Base',
    url: 'https://kb.example.com',
    description: 'Internal knowledge base articles',
    status: 'paused',
    documentCount: 89,
    createdAt: '2024-01-20T10:00:00Z',
    updatedAt: '2024-01-20T11:15:00Z',
    progress: 45,
  },
  {
    id: 'job-004',
    name: 'Blog Articles',
    url: 'https://blog.example.com',
    description: 'Company blog posts and articles',
    status: 'failed',
    documentCount: 12,
    createdAt: '2024-01-22T08:00:00Z',
    updatedAt: '2024-01-22T08:25:00Z',
    progress: 15,
  },
];

// Mock stats
const MOCK_STATS: CrawlStats = {
  totalDocuments: 1247,
  newDocuments: 156,
  updatedDocuments: 89,
  failedDocuments: 23,
  lastUpdated: '2024-01-22T10:30:00Z',
};

// Mock logs
const MOCK_LOGS: LogEntry[] = [
  {
    id: 'log-001',
    timestamp: '2024-01-22T10:30:00Z',
    level: 'info',
    message: 'Crawler initialized successfully',
    source: 'crawler-core',
  },
  {
    id: 'log-002',
    timestamp: '2024-01-22T10:30:05Z',
    level: 'info',
    message: 'Starting crawl job: Documentation Portal',
    source: 'job-manager',
  },
  {
    id: 'log-003',
    timestamp: '2024-01-22T10:30:10Z',
    level: 'debug',
    message: 'Fetching: https://docs.example.com/getting-started',
    source: 'http-client',
  },
  {
    id: 'log-004',
    timestamp: '2024-01-22T10:30:15Z',
    level: 'info',
    message: 'Document processed: Getting Started Guide (2.5KB)',
    source: 'document-processor',
  },
  {
    id: 'log-005',
    timestamp: '2024-01-22T10:30:20Z',
    level: 'warning',
    message: 'Rate limit detected, throttling requests',
    source: 'http-client',
  },
  {
    id: 'log-006',
    timestamp: '2024-01-22T10:30:25Z',
    level: 'error',
    message: 'Failed to fetch: https://docs.example.com/private (403 Forbidden)',
    source: 'http-client',
  },
  {
    id: 'log-007',
    timestamp: '2024-01-22T10:30:30Z',
    level: 'info',
    message: 'Discovered 15 new links to crawl',
    source: 'link-extractor',
  },
  {
    id: 'log-008',
    timestamp: '2024-01-22T10:30:35Z',
    level: 'debug',
    message: 'Processing document: API Overview',
    source: 'document-processor',
  },
];

// Mutable jobs list for CRUD operations
let jobs = [...MOCK_JOBS];
let logs = [...MOCK_LOGS];
let nextJobId = 5;
let nextLogId = 9;

// Progress simulation interval
let progressInterval: ReturnType<typeof setInterval> | null = null;

const startProgressSimulation = () => {
  if (progressInterval) return;

  progressInterval = setInterval(() => {
    if (crawlerState.status === 'running' && crawlerState.progress < 100) {
      crawlerState.progress = Math.min(100, crawlerState.progress + Math.random() * 5);
      if (crawlerState.progress >= 100) {
        crawlerState.status = 'completed';
        crawlerState.currentUrl = null;
        stopProgressSimulation();
      }
    }
  }, 1000);
};

const stopProgressSimulation = () => {
  if (progressInterval) {
    clearInterval(progressInterval);
    progressInterval = null;
  }
};

export const imsHandlers = [
  // Get crawler status
  http.get('/api/v1/ims/status', async () => {
    await delay(200);
    return HttpResponse.json(crawlerState);
  }),

  // Start crawling
  http.post('/api/v1/ims/start', async () => {
    await delay(300);

    if (crawlerState.status === 'running') {
      return HttpResponse.json(
        { error: 'Crawler is already running', code: 'CRAWLER_ALREADY_RUNNING' },
        { status: 400 }
      );
    }

    crawlerState = {
      status: 'running',
      progress: 0,
      currentUrl: 'https://docs.example.com/index.html',
      startTime: new Date().toISOString(),
      estimatedRemaining: 3600,
    };

    // Add log entry
    logs.unshift({
      id: `log-${String(nextLogId++).padStart(3, '0')}`,
      timestamp: new Date().toISOString(),
      level: 'info',
      message: 'Crawler started',
      source: 'crawler-core',
    });

    startProgressSimulation();

    return HttpResponse.json({
      success: true,
      message: 'Crawler started successfully',
      status: crawlerState,
    });
  }),

  // Stop crawling
  http.post('/api/v1/ims/stop', async () => {
    await delay(300);

    if (crawlerState.status !== 'running' && crawlerState.status !== 'paused') {
      return HttpResponse.json(
        { error: 'Crawler is not running', code: 'CRAWLER_NOT_RUNNING' },
        { status: 400 }
      );
    }

    stopProgressSimulation();

    crawlerState = {
      ...crawlerState,
      status: 'idle',
      currentUrl: null,
      estimatedRemaining: null,
    };

    logs.unshift({
      id: `log-${String(nextLogId++).padStart(3, '0')}`,
      timestamp: new Date().toISOString(),
      level: 'info',
      message: 'Crawler stopped by user',
      source: 'crawler-core',
    });

    return HttpResponse.json({
      success: true,
      message: 'Crawler stopped successfully',
      status: crawlerState,
    });
  }),

  // Pause crawling
  http.post('/api/v1/ims/pause', async () => {
    await delay(200);

    if (crawlerState.status !== 'running') {
      return HttpResponse.json(
        { error: 'Crawler is not running', code: 'CRAWLER_NOT_RUNNING' },
        { status: 400 }
      );
    }

    stopProgressSimulation();
    crawlerState.status = 'paused';

    logs.unshift({
      id: `log-${String(nextLogId++).padStart(3, '0')}`,
      timestamp: new Date().toISOString(),
      level: 'info',
      message: 'Crawler paused',
      source: 'crawler-core',
    });

    return HttpResponse.json({
      success: true,
      message: 'Crawler paused successfully',
      status: crawlerState,
    });
  }),

  // Resume crawling
  http.post('/api/v1/ims/resume', async () => {
    await delay(200);

    if (crawlerState.status !== 'paused') {
      return HttpResponse.json(
        { error: 'Crawler is not paused', code: 'CRAWLER_NOT_PAUSED' },
        { status: 400 }
      );
    }

    crawlerState.status = 'running';
    startProgressSimulation();

    logs.unshift({
      id: `log-${String(nextLogId++).padStart(3, '0')}`,
      timestamp: new Date().toISOString(),
      level: 'info',
      message: 'Crawler resumed',
      source: 'crawler-core',
    });

    return HttpResponse.json({
      success: true,
      message: 'Crawler resumed successfully',
      status: crawlerState,
    });
  }),

  // Get jobs list
  http.get('/api/v1/ims/jobs', async ({ request }) => {
    await delay(300);

    const url = new URL(request.url);
    const status = url.searchParams.get('status');
    const page = parseInt(url.searchParams.get('page') || '1');
    const limit = parseInt(url.searchParams.get('limit') || '10');

    let filtered = [...jobs];

    if (status && status !== 'all') {
      filtered = filtered.filter((job) => job.status === status);
    }

    // Sort by createdAt descending
    filtered.sort((a, b) => new Date(b.createdAt).getTime() - new Date(a.createdAt).getTime());

    const total = filtered.length;
    const start = (page - 1) * limit;
    const items = filtered.slice(start, start + limit);

    return HttpResponse.json({
      items,
      total,
      page,
      limit,
      totalPages: Math.ceil(total / limit),
    });
  }),

  // Create new job
  http.post('/api/v1/ims/jobs', async ({ request }) => {
    await delay(400);

    const body = (await request.json()) as {
      name: string;
      url: string;
      description?: string;
    };

    if (!body.url || !body.name) {
      return HttpResponse.json(
        { error: 'URL and name are required', code: 'VALIDATION_ERROR' },
        { status: 400 }
      );
    }

    const newJob: CrawlJob = {
      id: `job-${String(nextJobId++).padStart(3, '0')}`,
      name: body.name,
      url: body.url,
      description: body.description || '',
      status: 'pending',
      documentCount: 0,
      createdAt: new Date().toISOString(),
      updatedAt: new Date().toISOString(),
      progress: 0,
    };

    jobs.unshift(newJob);

    logs.unshift({
      id: `log-${String(nextLogId++).padStart(3, '0')}`,
      timestamp: new Date().toISOString(),
      level: 'info',
      message: `New crawl job created: ${body.name}`,
      source: 'job-manager',
    });

    return HttpResponse.json(newJob, { status: 201 });
  }),

  // Get single job
  http.get('/api/v1/ims/jobs/:id', async ({ params }) => {
    await delay(200);

    const job = jobs.find((j) => j.id === params.id);

    if (!job) {
      return HttpResponse.json(
        { error: 'Job not found', code: 'JOB_NOT_FOUND' },
        { status: 404 }
      );
    }

    return HttpResponse.json(job);
  }),

  // Delete job
  http.delete('/api/v1/ims/jobs/:id', async ({ params }) => {
    await delay(300);

    const index = jobs.findIndex((j) => j.id === params.id);

    if (index === -1) {
      return HttpResponse.json(
        { error: 'Job not found', code: 'JOB_NOT_FOUND' },
        { status: 404 }
      );
    }

    const deletedJob = jobs[index];
    jobs.splice(index, 1);

    logs.unshift({
      id: `log-${String(nextLogId++).padStart(3, '0')}`,
      timestamp: new Date().toISOString(),
      level: 'info',
      message: `Crawl job deleted: ${deletedJob.name}`,
      source: 'job-manager',
    });

    return HttpResponse.json({ success: true, message: 'Job deleted successfully' });
  }),

  // Get stats
  http.get('/api/v1/ims/stats', async () => {
    await delay(200);
    return HttpResponse.json({
      ...MOCK_STATS,
      lastUpdated: new Date().toISOString(),
    });
  }),

  // Get settings
  http.get('/api/v1/ims/settings', async () => {
    await delay(150);
    return HttpResponse.json(crawlerSettings);
  }),

  // Update settings
  http.put('/api/v1/ims/settings', async ({ request }) => {
    await delay(300);

    const body = (await request.json()) as Partial<CrawlerSettings>;

    crawlerSettings = {
      ...crawlerSettings,
      ...body,
    };

    logs.unshift({
      id: `log-${String(nextLogId++).padStart(3, '0')}`,
      timestamp: new Date().toISOString(),
      level: 'info',
      message: 'Crawler settings updated',
      source: 'settings-manager',
    });

    return HttpResponse.json({
      success: true,
      settings: crawlerSettings,
    });
  }),

  // Get logs
  http.get('/api/v1/ims/logs', async ({ request }) => {
    await delay(200);

    const url = new URL(request.url);
    const level = url.searchParams.get('level');
    const limit = parseInt(url.searchParams.get('limit') || '50');

    let filtered = [...logs];

    if (level && level !== 'all') {
      filtered = filtered.filter((log) => log.level === level);
    }

    return HttpResponse.json({
      items: filtered.slice(0, limit),
      total: filtered.length,
    });
  }),

  // Clear logs
  http.delete('/api/v1/ims/logs', async () => {
    await delay(200);
    logs = [];
    return HttpResponse.json({ success: true, message: 'Logs cleared successfully' });
  }),
];
