/**
 * Knowledge Base Mock API Handlers
 *
 * MSW handlers for knowledge base endpoints
 */

import { http, HttpResponse, delay } from 'msw';

// Mock knowledge articles
const MOCK_ARTICLES = [
  {
    id: 'kb-001',
    title: 'Getting Started with KMS Portal',
    summary: 'Learn how to navigate and use the KMS Portal effectively.',
    content: `# Getting Started with KMS Portal

Welcome to the KMS Portal! This guide will help you get started with the platform.

## Key Features

1. **Knowledge Base** - Search and browse documentation
2. **AI Assistant** - Ask questions and get intelligent answers
3. **IMS Crawler** - Manage document crawling jobs
4. **AI Studio** - Create and explore mindmaps

## Quick Start

1. Login with your credentials
2. Navigate to the Knowledge Base
3. Use the search bar or browse categories
4. Click on an article to read more

For more help, contact support@kms.local`,
    category: 'guides',
    tags: ['getting-started', 'basics', 'tutorial'],
    author: 'Admin User',
    createdAt: '2024-01-15T09:00:00Z',
    updatedAt: '2024-01-20T14:30:00Z',
    views: 1250,
    helpful: 45,
    notHelpful: 3,
  },
  {
    id: 'kb-002',
    title: 'Understanding RAG Technology',
    summary: 'Retrieval-Augmented Generation explained for enterprise use cases.',
    content: `# Understanding RAG Technology

RAG (Retrieval-Augmented Generation) combines the power of large language models with your organization's knowledge base.

## How RAG Works

1. **Retrieval** - When you ask a question, the system searches your documents
2. **Augmentation** - Relevant documents are provided as context to the AI
3. **Generation** - The AI generates a response based on your documents

## Benefits

- Accurate, up-to-date answers from your own data
- Reduced hallucinations compared to pure LLM responses
- Citations and source tracking
- Enterprise security and privacy`,
    category: 'documents',
    tags: ['rag', 'ai', 'technology'],
    author: 'Test User',
    createdAt: '2024-01-10T11:00:00Z',
    updatedAt: '2024-01-18T16:45:00Z',
    views: 890,
    helpful: 32,
    notHelpful: 2,
  },
  {
    id: 'kb-003',
    title: 'IMS Crawler Configuration Guide',
    summary: 'Configure and manage IMS crawling jobs for document ingestion.',
    content: `# IMS Crawler Configuration Guide

The IMS Crawler helps you automatically ingest documents from various sources.

## Configuration Options

### Crawl Depth
- Set the maximum depth for following links
- Default: 3 levels

### Crawl Interval
- Schedule regular crawls
- Options: Hourly, Daily, Weekly

### Document Types
- PDF, DOC, DOCX
- HTML, Markdown
- Plain text

## Best Practices

1. Start with a shallow crawl depth
2. Review crawled documents regularly
3. Set up appropriate filters
4. Monitor crawl status`,
    category: 'guides',
    tags: ['ims', 'crawler', 'configuration'],
    author: 'Admin User',
    createdAt: '2024-01-08T10:00:00Z',
    updatedAt: '2024-01-22T09:15:00Z',
    views: 567,
    helpful: 28,
    notHelpful: 1,
  },
  {
    id: 'kb-004',
    title: 'Frequently Asked Questions',
    summary: 'Common questions and answers about the KMS Portal.',
    content: `# Frequently Asked Questions

## General

**Q: How do I reset my password?**
A: Contact your administrator or use the "Forgot Password" link on the login page.

**Q: What browsers are supported?**
A: Chrome, Firefox, Safari, and Edge (latest versions).

## AI Assistant

**Q: How accurate are the AI responses?**
A: Responses are based on your organization's documents. Always verify critical information.

**Q: Can I provide feedback on responses?**
A: Yes, use the thumbs up/down buttons to rate responses.`,
    category: 'faqs',
    tags: ['faq', 'help', 'support'],
    author: 'Admin User',
    createdAt: '2024-01-05T08:00:00Z',
    updatedAt: '2024-01-21T11:30:00Z',
    views: 2100,
    helpful: 89,
    notHelpful: 5,
  },
  {
    id: 'kb-005',
    title: 'Security and Privacy Policy',
    summary: 'Information about data security and privacy measures.',
    content: `# Security and Privacy Policy

## Data Protection

Your data is protected with enterprise-grade security measures:

- End-to-end encryption
- Role-based access control
- Audit logging
- Regular security assessments

## Privacy

- Data stays within your organization
- No external data sharing
- GDPR compliant
- SOC 2 certified`,
    category: 'policies',
    tags: ['security', 'privacy', 'compliance'],
    author: 'Admin User',
    createdAt: '2024-01-01T00:00:00Z',
    updatedAt: '2024-01-15T10:00:00Z',
    views: 750,
    helpful: 41,
    notHelpful: 0,
  },
];

// Mock categories
const MOCK_CATEGORIES = [
  { id: 'all', name: 'All', count: MOCK_ARTICLES.length },
  { id: 'documents', name: 'Documents', count: 1 },
  { id: 'faqs', name: 'FAQs', count: 1 },
  { id: 'guides', name: 'Guides', count: 2 },
  { id: 'policies', name: 'Policies', count: 1 },
];

export const knowledgeHandlers = [
  // Get articles list
  http.get('/api/v1/knowledge/articles', async ({ request }) => {
    await delay(300);

    const url = new URL(request.url);
    const category = url.searchParams.get('category') || 'all';
    const search = url.searchParams.get('search') || '';
    const page = parseInt(url.searchParams.get('page') || '1');
    const limit = parseInt(url.searchParams.get('limit') || '10');

    let filtered = [...MOCK_ARTICLES];

    // Filter by category
    if (category !== 'all') {
      filtered = filtered.filter((a) => a.category === category);
    }

    // Filter by search
    if (search) {
      const searchLower = search.toLowerCase();
      filtered = filtered.filter(
        (a) =>
          a.title.toLowerCase().includes(searchLower) ||
          a.summary.toLowerCase().includes(searchLower) ||
          a.tags.some((t) => t.toLowerCase().includes(searchLower))
      );
    }

    // Pagination
    const total = filtered.length;
    const start = (page - 1) * limit;
    const items = filtered.slice(start, start + limit);

    return HttpResponse.json({
      items: items.map(({ content, ...rest }) => rest), // Exclude full content in list
      total,
      page,
      limit,
      totalPages: Math.ceil(total / limit),
    });
  }),

  // Get single article
  http.get('/api/v1/knowledge/articles/:id', async ({ params }) => {
    await delay(200);

    const article = MOCK_ARTICLES.find((a) => a.id === params.id);

    if (!article) {
      return HttpResponse.json(
        { error: 'Article not found', code: 'ARTICLE_NOT_FOUND' },
        { status: 404 }
      );
    }

    return HttpResponse.json(article);
  }),

  // Get categories
  http.get('/api/v1/knowledge/categories', async () => {
    await delay(100);
    return HttpResponse.json(MOCK_CATEGORIES);
  }),

  // Rate article
  http.post('/api/v1/knowledge/articles/:id/rate', async ({ params, request }) => {
    await delay(200);

    const body = (await request.json()) as { helpful: boolean };
    const article = MOCK_ARTICLES.find((a) => a.id === params.id);

    if (!article) {
      return HttpResponse.json(
        { error: 'Article not found', code: 'ARTICLE_NOT_FOUND' },
        { status: 404 }
      );
    }

    // Update counts (in mock, just return success)
    return HttpResponse.json({
      success: true,
      helpful: body.helpful ? article.helpful + 1 : article.helpful,
      notHelpful: body.helpful ? article.notHelpful : article.notHelpful + 1,
    });
  }),

  // Search suggestions
  http.get('/api/v1/knowledge/suggestions', async ({ request }) => {
    await delay(150);

    const url = new URL(request.url);
    const query = url.searchParams.get('q') || '';

    if (query.length < 2) {
      return HttpResponse.json([]);
    }

    const queryLower = query.toLowerCase();
    const suggestions = MOCK_ARTICLES.filter(
      (a) =>
        a.title.toLowerCase().includes(queryLower) ||
        a.tags.some((t) => t.toLowerCase().includes(queryLower))
    )
      .slice(0, 5)
      .map((a) => ({ id: a.id, title: a.title, category: a.category }));

    return HttpResponse.json(suggestions);
  }),
];
