/**
 * Chat/RAG Mock API Handlers
 *
 * MSW handlers for AI chat and RAG query endpoints
 */

import { http, HttpResponse, delay } from 'msw';

// Mock chat responses
const MOCK_RESPONSES: Record<string, string> = {
  default: `I found some relevant information in your knowledge base.

Based on the documents I reviewed, here's what I can tell you:

1. **Overview**: The KMS Portal provides comprehensive knowledge management capabilities.

2. **Key Features**:
   - Document search and retrieval
   - AI-powered question answering
   - Mindmap visualization
   - IMS document crawling

3. **Getting Started**: You can begin by exploring the Knowledge Base section or asking me specific questions.

Is there anything specific you'd like to know more about?`,

  rag: `According to your organization's documentation:

**RAG (Retrieval-Augmented Generation)** is a technology that combines:
- Large Language Models (LLMs)
- Your organization's knowledge base

This ensures responses are grounded in your actual data, reducing hallucinations and providing accurate, verifiable information.

**Sources:**
- Understanding RAG Technology (kb-002)
- Getting Started Guide (kb-001)`,

  security: `Based on your security policies:

**Data Protection Measures:**
1. End-to-end encryption for all data in transit and at rest
2. Role-based access control (RBAC)
3. Comprehensive audit logging
4. Regular security assessments

**Compliance:**
- GDPR compliant
- SOC 2 certified

For more details, see the Security and Privacy Policy document.`,

  ims: `The IMS Crawler allows you to:

1. **Configure Crawl Jobs**
   - Set crawl depth (recommended: 3 levels)
   - Schedule intervals (hourly, daily, weekly)
   - Filter document types

2. **Supported Formats**
   - PDF, DOC, DOCX
   - HTML, Markdown
   - Plain text files

3. **Best Practices**
   - Start with shallow crawl depth
   - Review documents regularly
   - Monitor job status

See the IMS Crawler Configuration Guide for detailed setup instructions.`,

  code: `Here's an example of how to use the API:

\`\`\`python
import requests

# Initialize the client
client = KMSClient(
    api_key="your-api-key",
    base_url="https://api.kms-portal.com"
)

# Query the knowledge base
response = client.query(
    query="How do I configure IMS Crawler?",
    strategy="hybrid"
)

print(response.answer)
print(response.sources)
\`\`\`

You can also use the REST API directly with \`fetch\` or \`axios\`.`,
};

// Detect intent from message
function detectIntent(message: string): string {
  const messageLower = message.toLowerCase();

  if (messageLower.includes('rag') || messageLower.includes('retrieval')) {
    return 'rag';
  }
  if (
    messageLower.includes('security') ||
    messageLower.includes('privacy') ||
    messageLower.includes('compliance')
  ) {
    return 'security';
  }
  if (messageLower.includes('ims') || messageLower.includes('crawler') || messageLower.includes('crawl')) {
    return 'ims';
  }
  if (messageLower.includes('code') || messageLower.includes('api') || messageLower.includes('example')) {
    return 'code';
  }

  return 'default';
}

// Mock sources for citations
const MOCK_SOURCES = [
  { id: 'kb-001', title: 'Getting Started with KMS Portal', relevance: 0.95, snippet: 'The KMS Portal is your central hub for knowledge management...' },
  { id: 'kb-002', title: 'Understanding RAG Technology', relevance: 0.88, snippet: 'RAG combines retrieval and generation for accurate answers...' },
  { id: 'kb-003', title: 'IMS Crawler Configuration Guide', relevance: 0.82, snippet: 'Configure your crawler to index documents automatically...' },
  { id: 'kb-004', title: 'Security and Privacy Policy', relevance: 0.79, snippet: 'Our security measures ensure your data is protected...' },
  { id: 'kb-005', title: 'API Integration Guide', relevance: 0.75, snippet: 'Integrate KMS Portal with your existing systems using our API...' },
];

// Mock conversation messages
const MOCK_CONVERSATION_MESSAGES: Record<string, any[]> = {
  'conv-001': [
    {
      id: 'msg-001-1',
      role: 'user',
      content: 'How do I use the knowledge base?',
      timestamp: '2024-01-20T10:00:00Z',
    },
    {
      id: 'msg-001-2',
      role: 'assistant',
      content: MOCK_RESPONSES.default,
      sources: [MOCK_SOURCES[0], MOCK_SOURCES[1]],
      timestamp: '2024-01-20T10:00:05Z',
    },
    {
      id: 'msg-001-3',
      role: 'user',
      content: 'Tell me more about RAG technology',
      timestamp: '2024-01-20T10:15:00Z',
    },
    {
      id: 'msg-001-4',
      role: 'assistant',
      content: MOCK_RESPONSES.rag,
      sources: [MOCK_SOURCES[1], MOCK_SOURCES[0]],
      timestamp: '2024-01-20T10:15:05Z',
    },
    {
      id: 'msg-001-5',
      role: 'user',
      content: 'What about security?',
      timestamp: '2024-01-20T10:30:00Z',
    },
  ],
  'conv-002': [
    {
      id: 'msg-002-1',
      role: 'user',
      content: 'What is RAG?',
      timestamp: '2024-01-19T14:00:00Z',
    },
    {
      id: 'msg-002-2',
      role: 'assistant',
      content: MOCK_RESPONSES.rag,
      sources: [MOCK_SOURCES[1]],
      timestamp: '2024-01-19T14:00:05Z',
    },
    {
      id: 'msg-002-3',
      role: 'user',
      content: 'How does it compare to traditional search?',
      timestamp: '2024-01-19T14:15:00Z',
    },
  ],
};

export const chatHandlers = [
  // Chat/Query endpoint
  http.post('/api/v1/query', async ({ request }) => {
    await delay(1000); // Simulate LLM processing time

    const body = (await request.json()) as { query: string; conversationId?: string };
    const { query, conversationId } = body;

    const intent = detectIntent(query);
    const response = MOCK_RESPONSES[intent];

    // Select relevant sources based on intent
    const sources =
      intent === 'default'
        ? MOCK_SOURCES.slice(0, 2)
        : intent === 'rag'
          ? [MOCK_SOURCES[1], MOCK_SOURCES[0]]
          : intent === 'ims'
            ? [MOCK_SOURCES[2], MOCK_SOURCES[0]]
            : intent === 'security'
              ? [MOCK_SOURCES[3], MOCK_SOURCES[0]]
              : intent === 'code'
                ? [MOCK_SOURCES[4], MOCK_SOURCES[0]]
                : [MOCK_SOURCES[0]];

    return HttpResponse.json({
      id: `msg-${Date.now()}`,
      conversationId: conversationId || `conv-${Date.now()}`,
      query,
      response,
      sources: sources.map((s) => ({
        ...s,
        snippet: s.snippet || `Relevant excerpt from "${s.title}"...`,
      })),
      strategy: 'HYBRID',
      processingTime: Math.random() * 2 + 0.5, // 0.5-2.5 seconds
      timestamp: new Date().toISOString(),
    });
  }),

  // Streaming chat endpoint (simulated)
  http.post('/api/v1/query/stream', async ({ request }) => {
    const body = (await request.json()) as { query: string };
    const intent = detectIntent(body.query);
    const fullResponse = MOCK_RESPONSES[intent];

    // Return streaming response simulation
    const encoder = new TextEncoder();
    const stream = new ReadableStream({
      async start(controller) {
        const words = fullResponse.split(' ');

        for (let i = 0; i < words.length; i++) {
          await new Promise((resolve) => setTimeout(resolve, 50)); // 50ms per word
          const chunk = JSON.stringify({
            type: 'content',
            content: words[i] + (i < words.length - 1 ? ' ' : ''),
          });
          controller.enqueue(encoder.encode(`data: ${chunk}\n\n`));
        }

        // Send sources at the end
        const sources =
          intent === 'default'
            ? MOCK_SOURCES.slice(0, 2)
            : intent === 'rag'
              ? [MOCK_SOURCES[1], MOCK_SOURCES[0]]
              : intent === 'ims'
                ? [MOCK_SOURCES[2], MOCK_SOURCES[0]]
                : intent === 'security'
                  ? [MOCK_SOURCES[3], MOCK_SOURCES[0]]
                  : intent === 'code'
                    ? [MOCK_SOURCES[4], MOCK_SOURCES[0]]
                    : [MOCK_SOURCES[0]];

        controller.enqueue(
          encoder.encode(
            `data: ${JSON.stringify({ type: 'sources', sources })}\n\n`
          )
        );

        controller.enqueue(encoder.encode('data: [DONE]\n\n'));
        controller.close();
      },
    });

    return new HttpResponse(stream, {
      headers: {
        'Content-Type': 'text/event-stream',
        'Cache-Control': 'no-cache',
        Connection: 'keep-alive',
      },
    });
  }),

  // Get conversation history
  http.get('/api/v1/conversations', async () => {
    await delay(200);

    return HttpResponse.json({
      conversations: [
        {
          id: 'conv-001',
          title: 'Getting started questions',
          lastMessage: 'What about security?',
          messageCount: 5,
          createdAt: '2024-01-20T10:00:00Z',
          updatedAt: '2024-01-20T10:30:00Z',
        },
        {
          id: 'conv-002',
          title: 'RAG technology discussion',
          lastMessage: 'How does it compare to traditional search?',
          messageCount: 3,
          createdAt: '2024-01-19T14:00:00Z',
          updatedAt: '2024-01-19T14:15:00Z',
        },
      ],
    });
  }),

  // Get conversation messages by ID
  http.get('/api/v1/conversations/:conversationId/messages', async ({ params }) => {
    await delay(300);

    const { conversationId } = params;
    const messages = MOCK_CONVERSATION_MESSAGES[conversationId as string] || [];

    return HttpResponse.json({
      conversationId,
      messages,
      totalCount: messages.length,
    });
  }),

  // Delete conversation
  http.delete('/api/v1/conversations/:conversationId', async ({ params }) => {
    await delay(200);

    const { conversationId } = params;

    return HttpResponse.json({
      success: true,
      deletedId: conversationId,
      message: 'Conversation deleted successfully',
    });
  }),

  // Get suggested questions
  http.get('/api/v1/query/suggestions', async () => {
    await delay(100);

    return HttpResponse.json([
      'How do I get started with the KMS Portal?',
      'What is RAG and how does it work?',
      'How do I configure the IMS Crawler?',
      'What security measures are in place?',
      'How can I search for documents?',
    ]);
  }),

  // Submit feedback for a message
  http.post('/api/v1/messages/:messageId/feedback', async ({ params, request }) => {
    await delay(100);

    const { messageId } = params;
    const body = (await request.json()) as { type: 'up' | 'down'; comment?: string };

    return HttpResponse.json({
      success: true,
      messageId,
      feedback: body.type,
      message: 'Feedback submitted successfully',
    });
  }),
];
