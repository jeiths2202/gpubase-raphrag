import React, { useState, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { useNavigate } from 'react-router-dom';
import { useAuthStore } from '../store/authStore';
import { useTranslation } from '../hooks/useTranslation';
import { LANGUAGES, LanguageCode } from '../i18n/types';

// Types
interface Project {
  id: string;
  name: string;
  description?: string;
  color?: string;
  document_count: number;
  note_count: number;
  created_at: string;
}

interface Note {
  id: string;
  title: string;
  preview: string;
  note_type: string;
  folder_name?: string;
  tags: string[];
  is_pinned: boolean;
  created_at: string;
  updated_at: string;
}

interface Folder {
  id: string;
  name: string;
  note_count: number;
  children: Folder[];
  color?: string;
}

interface Document {
  id: string;
  filename: string;
  original_name: string;
  status: string;
  chunks_count: number;
  document_type?: string;
  processing_mode?: string;
  vlm_processed?: boolean;
  file_size?: number;
  mime_type?: string;
}

// Supported file formats
const SUPPORTED_FORMATS = {
  pdf: { extensions: ['.pdf'], icon: '📄', color: '#E74C3C' },
  word: { extensions: ['.doc', '.docx'], icon: '📝', color: '#2B579A' },
  excel: { extensions: ['.xls', '.xlsx'], icon: '📊', color: '#217346' },
  powerpoint: { extensions: ['.ppt', '.pptx'], icon: '📽️', color: '#D24726' },
  text: { extensions: ['.txt', '.md', '.markdown'], icon: '📃', color: '#6C757D' },
  data: { extensions: ['.csv', '.json'], icon: '📋', color: '#17A2B8' },
  image: { extensions: ['.png', '.jpg', '.jpeg', '.gif', '.bmp', '.tiff', '.webp'], icon: '🖼️', color: '#9B59B6' },
  html: { extensions: ['.html', '.htm'], icon: '🌐', color: '#E44D26' }
};

const getFileTypeInfo = (filename: string): { icon: string; color: string; type: string } => {
  const ext = filename.toLowerCase().substring(filename.lastIndexOf('.'));
  for (const [type, info] of Object.entries(SUPPORTED_FORMATS)) {
    if (info.extensions.includes(ext)) {
      return { icon: info.icon, color: info.color, type };
    }
  }
  return { icon: '📄', color: '#6C757D', type: 'unknown' };
};

const formatFileSize = (bytes: number): string => {
  if (bytes < 1024) return bytes + ' B';
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB';
  return (bytes / (1024 * 1024)).toFixed(1) + ' MB';
};

interface ContentItem {
  id: string;
  content_type: string;
  status: string;
  title: string;
  created_at: string;
}

interface ChatMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  sources?: { doc_name: string; chunk_index: number; content: string; score: number }[];
  timestamp: Date;
}

interface Conversation {
  id: string;
  title: string;
  queries_count: number;
  last_query_at?: string;
}

// Knowledge Graph types
interface KGEntity {
  id: string;
  label: string;
  entity_type: string;
  properties: Record<string, any>;
  confidence: number;
  x?: number;
  y?: number;
  color?: string;
}

interface KGRelationship {
  id: string;
  source_id: string;
  target_id: string;
  relation_type: string;
  weight: number;
  confidence: number;
}

interface KnowledgeGraphData {
  id: string;
  name: string;
  description?: string;
  entities: KGEntity[];
  relationships: KGRelationship[];
  entity_count: number;
  relationship_count: number;
  source_query?: string;
  created_at: string;
}

// Knowledge Article types
type KnowledgeStatus = 'draft' | 'pending' | 'in_review' | 'approved' | 'rejected' | 'published';
type KnowledgeCategory = 'technical' | 'process' | 'guideline' | 'troubleshooting' | 'best_practice' | 'tutorial' | 'faq' | 'announcement' | 'research' | 'other';
type SupportedLanguage = 'ko' | 'ja' | 'en';

interface KnowledgeTranslation {
  language: SupportedLanguage;
  title: string;
  content: string;
  summary?: string;
}

interface ReviewComment {
  id: string;
  reviewer_id: string;
  reviewer_name: string;
  comment: string;
  action: string;
  created_at: string;
}

interface KnowledgeArticle {
  id: string;
  title: string;
  content: string;
  summary?: string;
  primary_language: SupportedLanguage;
  category: KnowledgeCategory;
  tags: string[];
  author_id: string;
  author_name: string;
  author_department?: string;
  status: KnowledgeStatus;
  reviewer_id?: string;
  reviewer_name?: string;
  review_comments: ReviewComment[];
  translations: Record<string, KnowledgeTranslation>;
  view_count: number;
  recommendation_count: number;
  created_at: string;
  published_at?: string;
}

interface TopContributor {
  user_id: string;
  username: string;
  department?: string;
  total_recommendations: number;
  article_count: number;
  rank: number;
}

interface CategoryOption {
  value: KnowledgeCategory;
  label: string;
}

// Notification types
interface Notification {
  id: string;
  user_id: string;
  type: string;
  title: string;
  message: string;
  reference_type?: string;
  reference_id?: string;
  is_read: boolean;
  created_at: string;
}

type TabType = 'chat' | 'documents' | 'web-sources' | 'notes' | 'content' | 'projects' | 'mindmap' | 'knowledge-graph' | 'knowledge-articles';

// Web Source types
interface WebSource {
  id: string;
  url: string;
  display_name: string;
  domain: string;
  status: 'pending' | 'fetching' | 'extracting' | 'chunking' | 'embedding' | 'ready' | 'error' | 'stale';
  metadata: {
    title?: string;
    description?: string;
    author?: string;
    content_type: string;
    language?: string;
  };
  stats: {
    word_count: number;
    chunk_count: number;
    fetch_time_ms: number;
  };
  tags: string[];
  error_message?: string;
  created_at: string;
  fetched_at?: string;
}
type ThemeType = 'dark' | 'light';

const API_BASE = '/api/v1';

const KnowledgeApp: React.FC = () => {
  const navigate = useNavigate();
  const { user, logout } = useAuthStore();

  // Theme state
  const [theme, setTheme] = useState<ThemeType>('dark');

  // Tab state
  const [activeTab, setActiveTab] = useState<TabType>('chat');

  // Projects state
  const [projects, setProjects] = useState<Project[]>([]);
  const [selectedProject, setSelectedProject] = useState<Project | null>(null);

  // Documents state
  const [documents, setDocuments] = useState<Document[]>([]);
  const [selectedDocuments, setSelectedDocuments] = useState<string[]>([]);

  // Notes state
  const [notes, setNotes] = useState<Note[]>([]);
  const [folders, setFolders] = useState<Folder[]>([]);
  const [selectedFolder, setSelectedFolder] = useState<string | null>(null);
  const [selectedNote, setSelectedNote] = useState<Note | null>(null);
  const [noteContent, setNoteContent] = useState('');
  const [noteTitle, setNoteTitle] = useState('');

  // Content state
  const [contents, setContents] = useState<ContentItem[]>([]);
  const [selectedContent, setSelectedContent] = useState<ContentItem | null>(null);
  const [contentData, setContentData] = useState<any>(null);
  const [generatingContent, setGeneratingContent] = useState(false);

  // Chat state
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [inputMessage, setInputMessage] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [selectedConversation, setSelectedConversation] = useState<string | null>(null);
  const [suggestedQuestions, setSuggestedQuestions] = useState<string[]>([]);

  // Session document state (for chat context)
  const [sessionId] = useState<string>(`session_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`);
  const [sessionDocuments, setSessionDocuments] = useState<{
    id: string;
    filename: string;
    status: string;
    chunk_count: number;
    word_count: number;
  }[]>([]);
  const [showPasteModal, setShowPasteModal] = useState(false);
  const [pasteContent, setPasteContent] = useState('');
  const [pasteTitle, setPasteTitle] = useState('');
  const [uploadingSessionDoc, setUploadingSessionDoc] = useState(false);
  const [dragOver, setDragOver] = useState(false);

  // Search state
  const [searchQuery, setSearchQuery] = useState('');
  const [searchResults, setSearchResults] = useState<any[]>([]);

  // Knowledge Graph state
  const [knowledgeGraphs, setKnowledgeGraphs] = useState<KnowledgeGraphData[]>([]);
  const [selectedKG, setSelectedKG] = useState<KnowledgeGraphData | null>(null);
  const [kgQuery, setKgQuery] = useState('');
  const [buildingKG, setBuildingKG] = useState(false);
  const [queryingKG, setQueryingKG] = useState(false);
  const [kgAnswer, setKgAnswer] = useState<string | null>(null);

  // Knowledge Article state
  const [knowledgeArticles, setKnowledgeArticles] = useState<KnowledgeArticle[]>([]);
  const [selectedArticle, setSelectedArticle] = useState<KnowledgeArticle | null>(null);
  const [articleLanguage, setArticleLanguage] = useState<SupportedLanguage>('ko');
  const [showCreateArticle, setShowCreateArticle] = useState(false);
  const [newArticle, setNewArticle] = useState({
    title: '',
    content: '',
    summary: '',
    category: 'technical' as KnowledgeCategory,
    tags: [] as string[]
  });
  const [savingArticle, setSavingArticle] = useState(false);
  const [categories, setCategories] = useState<CategoryOption[]>([]);
  const [topContributors, setTopContributors] = useState<TopContributor[]>([]);
  const [pendingReviews, setPendingReviews] = useState<KnowledgeArticle[]>([]);
  const [reviewComment, setReviewComment] = useState('');

  // Notification state
  const [notifications, setNotifications] = useState<Notification[]>([]);
  const [unreadCount, setUnreadCount] = useState(0);
  const [showNotifications, setShowNotifications] = useState(false);

  // Source panel state
  const [showSourcePanel, setShowSourcePanel] = useState(false);
  const [selectedSource, setSelectedSource] = useState<any>(null);

  // Sidebar state
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);

  // Settings popup state
  const [showSettingsPopup, setShowSettingsPopup] = useState(false);

  // Translation hook
  const { language, setLanguage, t } = useTranslation();

  // Upload state
  const [showUploadModal, setShowUploadModal] = useState(false);
  const [uploadFile, setUploadFile] = useState<File | null>(null);
  const [uploadSettings, setUploadSettings] = useState({
    processingMode: 'text_only' as 'text_only' | 'vlm_enhanced' | 'multimodal' | 'ocr',
    enableVLM: false,
    extractTables: true,
    extractImages: true,
    language: 'auto'
  });
  const [uploading, setUploading] = useState(false);
  const [uploadProgress, setUploadProgress] = useState<string | null>(null);

  // Web Source state
  const [webSources, setWebSources] = useState<WebSource[]>([]);
  const [showAddUrlModal, setShowAddUrlModal] = useState(false);
  const [newUrls, setNewUrls] = useState('');
  const [addingUrls, setAddingUrls] = useState(false);
  const [webSourceTags, setWebSourceTags] = useState<string[]>([]);

  // External Connection state
  const [externalConnections, setExternalConnections] = useState<{
    id: string;
    resource_type: string;
    status: string;
    document_count: number;
    chunk_count: number;
    last_sync_at: string | null;
    error_message: string | null;
  }[]>([]);
  const [showExternalModal, setShowExternalModal] = useState(false);
  const [connectingResource, setConnectingResource] = useState<string | null>(null);
  const [syncingConnection, setSyncingConnection] = useState<string | null>(null);
  const [availableResources] = useState([
    { type: 'notion', name: 'Notion', icon: '📝', description: 'Notion 페이지 및 데이터베이스', authType: 'oauth2' },
    { type: 'github', name: 'GitHub', icon: '🐙', description: 'GitHub 저장소 문서', authType: 'oauth2' },
    { type: 'google_drive', name: 'Google Drive', icon: '📁', description: 'Google Drive 문서', authType: 'oauth2' },
    { type: 'onenote', name: 'OneNote', icon: '📔', description: 'Microsoft OneNote 노트북', authType: 'oauth2' },
    { type: 'confluence', name: 'Confluence', icon: '📚', description: 'Atlassian Confluence 페이지', authType: 'api_token' }
  ]);

  // Load initial data
  useEffect(() => {
    loadProjects();
    loadDocuments();
    loadConversations();
    loadNotifications();
    loadUnreadCount();
  }, []);

  useEffect(() => {
    if (activeTab === 'notes') {
      loadNotes();
      loadFolders();
    } else if (activeTab === 'content') {
      loadContents();
    } else if (activeTab === 'knowledge-graph') {
      loadKnowledgeGraphs();
    } else if (activeTab === 'knowledge-articles') {
      loadKnowledgeArticles();
      loadCategories();
      loadTopContributors();
      if (user?.role === 'senior' || user?.role === 'leader' || user?.role === 'admin') {
        loadPendingReviews();
      }
    } else if (activeTab === 'web-sources') {
      loadWebSources();
    }
  }, [activeTab, selectedProject]);

  // API calls
  const getAuthHeaders = () => {
    const token = localStorage.getItem('access_token');
    return {
      'Content-Type': 'application/json',
      'Authorization': `Bearer ${token}`
    };
  };

  const loadProjects = async () => {
    try {
      const res = await fetch(`${API_BASE}/projects?page=1&limit=50`, {
        headers: getAuthHeaders()
      });
      const data = await res.json();
      setProjects(data.data?.projects || []);
    } catch (error) {
      console.error('Failed to load projects:', error);
    }
  };

  const loadDocuments = async () => {
    try {
      const res = await fetch(`${API_BASE}/documents?page=1&limit=100`, {
        headers: getAuthHeaders()
      });
      const data = await res.json();
      setDocuments(data.data?.documents || []);
    } catch (error) {
      console.error('Failed to load documents:', error);
    }
  };

  const loadWebSources = async () => {
    try {
      const res = await fetch(`${API_BASE}/web-sources?page=1&limit=100`, {
        headers: getAuthHeaders()
      });
      const data = await res.json();
      setWebSources(data.data?.web_sources || []);
    } catch (error) {
      console.error('Failed to load web sources:', error);
    }
  };

  const addWebSources = async () => {
    if (!newUrls.trim()) return;

    setAddingUrls(true);
    try {
      const urls = newUrls.split('\n').map(u => u.trim()).filter(u => u);

      if (urls.length === 1) {
        // Single URL
        const res = await fetch(`${API_BASE}/web-sources`, {
          method: 'POST',
          headers: getAuthHeaders(),
          body: JSON.stringify({
            url: urls[0],
            tags: webSourceTags
          })
        });
        const data = await res.json();
        if (data.status === 'success') {
          setWebSources(prev => [data.data.web_source, ...prev]);
        }
      } else {
        // Multiple URLs
        const res = await fetch(`${API_BASE}/web-sources/bulk`, {
          method: 'POST',
          headers: getAuthHeaders(),
          body: JSON.stringify({
            urls: urls,
            tags: webSourceTags
          })
        });
        const data = await res.json();
        if (data.status === 'success') {
          setWebSources(prev => [...data.data.web_sources, ...prev]);
        }
      }

      setNewUrls('');
      setWebSourceTags([]);
      setShowAddUrlModal(false);
    } catch (error) {
      console.error('Failed to add web sources:', error);
    } finally {
      setAddingUrls(false);
    }
  };

  const refreshWebSource = async (id: string) => {
    try {
      const res = await fetch(`${API_BASE}/web-sources/${id}/refresh`, {
        method: 'POST',
        headers: getAuthHeaders(),
        body: JSON.stringify({ force: false })
      });
      const data = await res.json();
      if (data.status === 'success') {
        loadWebSources();
      }
    } catch (error) {
      console.error('Failed to refresh web source:', error);
    }
  };

  const deleteWebSource = async (id: string) => {
    try {
      const res = await fetch(`${API_BASE}/web-sources/${id}`, {
        method: 'DELETE',
        headers: getAuthHeaders()
      });
      const data = await res.json();
      if (data.status === 'success') {
        setWebSources(prev => prev.filter(ws => ws.id !== id));
      }
    } catch (error) {
      console.error('Failed to delete web source:', error);
    }
  };

  const loadNotes = async () => {
    try {
      const url = selectedProject
        ? `${API_BASE}/notes?project_id=${selectedProject.id}&page=1&limit=50`
        : `${API_BASE}/notes?page=1&limit=50`;
      const res = await fetch(url, { headers: getAuthHeaders() });
      const data = await res.json();
      setNotes(data.data?.notes || []);
    } catch (error) {
      console.error('Failed to load notes:', error);
    }
  };

  const loadFolders = async () => {
    try {
      const url = selectedProject
        ? `${API_BASE}/notes/folders?project_id=${selectedProject.id}`
        : `${API_BASE}/notes/folders`;
      const res = await fetch(url, { headers: getAuthHeaders() });
      const data = await res.json();
      setFolders(data.data?.folders || []);
    } catch (error) {
      console.error('Failed to load folders:', error);
    }
  };

  const loadContents = async () => {
    try {
      const res = await fetch(`${API_BASE}/content?page=1&limit=50`, {
        headers: getAuthHeaders()
      });
      const data = await res.json();
      setContents(data.data?.contents || []);
    } catch (error) {
      console.error('Failed to load contents:', error);
    }
  };

  const loadConversations = async () => {
    try {
      const res = await fetch(`${API_BASE}/conversations?page=1&limit=20`, {
        headers: getAuthHeaders()
      });
      const data = await res.json();
      setConversations(data.data?.conversations || []);
    } catch (error) {
      console.error('Failed to load conversations:', error);
    }
  };

  const loadContentDetail = async (contentId: string) => {
    try {
      const res = await fetch(`${API_BASE}/content/${contentId}`, {
        headers: getAuthHeaders()
      });
      const data = await res.json();
      setContentData(data.data?.content);
    } catch (error) {
      console.error('Failed to load content detail:', error);
    }
  };

  // Chat functions
  const sendMessage = async () => {
    if (!inputMessage.trim() || isLoading) return;

    const userMessage: ChatMessage = {
      id: `msg_${Date.now()}`,
      role: 'user',
      content: inputMessage,
      timestamp: new Date()
    };

    setMessages(prev => [...prev, userMessage]);
    setInputMessage('');
    setIsLoading(true);

    try {
      // Get current UI language for RAG response synchronization
      const uiLanguage = localStorage.getItem('kms-preferences')
        ? JSON.parse(localStorage.getItem('kms-preferences') || '{}').state?.language || 'auto'
        : 'auto';

      const res = await fetch(`${API_BASE}/query`, {
        method: 'POST',
        headers: getAuthHeaders(),
        body: JSON.stringify({
          question: inputMessage,
          strategy: 'auto',
          language: uiLanguage, // Sync RAG response with UI language
          options: {
            top_k: 5,
            include_sources: true,
            conversation_id: selectedConversation,
            // Session document options for priority RAG
            session_id: sessionDocuments.length > 0 ? sessionId : undefined,
            use_session_docs: sessionDocuments.length > 0,
            session_weight: 2.0
          }
        })
      });

      const data = await res.json();

      const assistantMessage: ChatMessage = {
        id: `msg_${Date.now()}_resp`,
        role: 'assistant',
        content: data.data?.answer || '응답을 생성할 수 없습니다.',
        sources: data.data?.sources?.map((s: any) => ({
          doc_name: s.doc_name,
          chunk_index: s.chunk_index,
          content: s.content,
          score: s.score,
          is_session_doc: s.is_session_doc,
          page_number: s.page_number
        })),
        timestamp: new Date()
      };

      setMessages(prev => [...prev, assistantMessage]);

      // Generate suggested questions
      generateSuggestedQuestions(inputMessage, data.data?.answer);

    } catch (error) {
      console.error('Failed to send message:', error);
      setMessages(prev => [...prev, {
        id: `msg_${Date.now()}_err`,
        role: 'assistant',
        content: '오류가 발생했습니다. 다시 시도해주세요.',
        timestamp: new Date()
      }]);
    } finally {
      setIsLoading(false);
    }
  };

  const generateSuggestedQuestions = (query: string, answer: string) => {
    const suggestions = [
      `${query}에 대해 더 자세히 알려주세요`,
      '관련된 예시를 보여주세요',
      '이 주제의 장단점은 무엇인가요?'
    ];
    setSuggestedQuestions(suggestions);
  };

  // Session document functions
  const uploadSessionFile = async (file: File) => {
    setUploadingSessionDoc(true);
    try {
      const formData = new FormData();
      formData.append('session_id', sessionId);
      formData.append('file', file);

      const res = await fetch(`${API_BASE}/session-documents/upload`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${localStorage.getItem('access_token')}`
        },
        body: formData
      });

      const data = await res.json();
      if (data.status === 'success') {
        // Add to session documents and poll for status
        setSessionDocuments(prev => [...prev, {
          id: data.data.document_id,
          filename: data.data.filename,
          status: 'processing',
          chunk_count: 0,
          word_count: 0
        }]);
        pollSessionDocumentStatus(data.data.document_id);
      }
    } catch (error) {
      console.error('Failed to upload session file:', error);
    } finally {
      setUploadingSessionDoc(false);
    }
  };

  const pasteSessionText = async () => {
    if (!pasteContent.trim()) return;
    setUploadingSessionDoc(true);
    try {
      const formData = new FormData();
      formData.append('session_id', sessionId);
      formData.append('content', pasteContent);
      formData.append('title', pasteTitle || 'Pasted Text');

      const res = await fetch(`${API_BASE}/session-documents/paste`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${localStorage.getItem('access_token')}`
        },
        body: formData
      });

      const data = await res.json();
      if (data.status === 'success') {
        setSessionDocuments(prev => [...prev, {
          id: data.data.document_id,
          filename: data.data.filename,
          status: 'processing',
          chunk_count: 0,
          word_count: data.data.word_count || 0
        }]);
        pollSessionDocumentStatus(data.data.document_id);
        setPasteContent('');
        setPasteTitle('');
        setShowPasteModal(false);
      }
    } catch (error) {
      console.error('Failed to paste session text:', error);
    } finally {
      setUploadingSessionDoc(false);
    }
  };

  const pollSessionDocumentStatus = async (docId: string) => {
    const checkStatus = async () => {
      try {
        const res = await fetch(`${API_BASE}/session-documents/${docId}/status`, {
          headers: getAuthHeaders()
        });
        const data = await res.json();

        if (data.data?.status === 'ready') {
          setSessionDocuments(prev => prev.map(d =>
            d.id === docId ? { ...d, status: 'ready', chunk_count: data.data.chunk_count } : d
          ));
        } else if (data.data?.status === 'error') {
          setSessionDocuments(prev => prev.map(d =>
            d.id === docId ? { ...d, status: 'error' } : d
          ));
        } else {
          setTimeout(checkStatus, 1000);
        }
      } catch (error) {
        console.error('Failed to check status:', error);
      }
    };
    checkStatus();
  };

  const removeSessionDocument = async (docId: string) => {
    try {
      await fetch(`${API_BASE}/session-documents/${docId}?session_id=${sessionId}`, {
        method: 'DELETE',
        headers: getAuthHeaders()
      });
      setSessionDocuments(prev => prev.filter(d => d.id !== docId));
    } catch (error) {
      console.error('Failed to remove session document:', error);
    }
  };

  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    setDragOver(true);
  };

  const handleDragLeave = (e: React.DragEvent) => {
    e.preventDefault();
    setDragOver(false);
  };

  const handleDrop = async (e: React.DragEvent) => {
    e.preventDefault();
    setDragOver(false);
    const files = e.dataTransfer.files;
    if (files.length > 0) {
      await uploadSessionFile(files[0]);
    }
  };

  // External Connection functions
  const loadExternalConnections = async () => {
    try {
      const userId = user?.id || user?.user_id;
      if (!userId) return;

      const res = await fetch(`${API_BASE}/external-connections?user_id=${userId}`, {
        headers: getAuthHeaders()
      });
      if (res.ok) {
        const data = await res.json();
        setExternalConnections(data.connections || []);
      }
    } catch (error) {
      console.error('Failed to load external connections:', error);
    }
  };

  const connectExternalResource = async (resourceType: string) => {
    setConnectingResource(resourceType);
    try {
      const userId = user?.id || user?.user_id;

      // Create connection
      const res = await fetch(`${API_BASE}/external-connections?user_id=${userId}`, {
        method: 'POST',
        headers: getAuthHeaders(),
        body: JSON.stringify({
          resource_type: resourceType,
          config: {}
        })
      });

      if (!res.ok) throw new Error('Failed to create connection');
      const connection = await res.json();

      // Get OAuth URL for OAuth-based resources
      const resource = availableResources.find(r => r.type === resourceType);
      if (resource?.authType === 'oauth2') {
        const redirectUri = `${window.location.origin}/oauth/callback`;
        const oauthRes = await fetch(
          `${API_BASE}/external-connections/${connection.id}/oauth-url?redirect_uri=${encodeURIComponent(redirectUri)}`,
          { headers: getAuthHeaders() }
        );

        if (oauthRes.ok) {
          const { oauth_url } = await oauthRes.json();
          // Store connection ID for callback
          sessionStorage.setItem('oauth_connection_id', connection.id);
          // Redirect to OAuth
          window.location.href = oauth_url;
        }
      } else {
        // API token auth - connection is already complete
        await loadExternalConnections();
        setShowExternalModal(false);
      }
    } catch (error) {
      console.error('Failed to connect external resource:', error);
      // Note: t() is available from useTranslation hook at component level
      alert(t('knowledge.external.connectionFailed' as keyof import('../i18n/types').TranslationKeys));
    } finally {
      setConnectingResource(null);
    }
  };

  const disconnectExternalResource = async (connectionId: string) => {
    if (!confirm(t('knowledge.external.disconnectConfirm' as keyof import('../i18n/types').TranslationKeys))) return;

    try {
      const res = await fetch(`${API_BASE}/external-connections/${connectionId}`, {
        method: 'DELETE',
        headers: getAuthHeaders()
      });

      if (res.ok) {
        setExternalConnections(prev => prev.filter(c => c.id !== connectionId));
      }
    } catch (error) {
      console.error('Failed to disconnect:', error);
    }
  };

  const syncExternalResource = async (connectionId: string, fullSync = false) => {
    setSyncingConnection(connectionId);
    try {
      const res = await fetch(`${API_BASE}/external-connections/${connectionId}/sync`, {
        method: 'POST',
        headers: getAuthHeaders(),
        body: JSON.stringify({ full_sync: fullSync })
      });

      if (res.ok) {
        await loadExternalConnections();
      }
    } catch (error) {
      console.error('Failed to sync:', error);
    } finally {
      setSyncingConnection(null);
    }
  };

  // Load external connections on mount
  useEffect(() => {
    if (user) {
      loadExternalConnections();
    }
  }, [user]);

  // Content generation
  const generateContent = async (type: string) => {
    if (selectedDocuments.length === 0) {
      alert('문서를 먼저 선택해주세요.');
      return;
    }

    setGeneratingContent(true);
    try {
      const res = await fetch(`${API_BASE}/content/generate`, {
        method: 'POST',
        headers: getAuthHeaders(),
        body: JSON.stringify({
          document_ids: selectedDocuments,
          content_type: type,
          language: 'auto'
        })
      });

      const data = await res.json();
      if (data.data?.content_id) {
        // Poll for completion
        pollContentStatus(data.data.content_id);
      }
    } catch (error) {
      console.error('Failed to generate content:', error);
    }
  };

  const pollContentStatus = async (contentId: string) => {
    const checkStatus = async () => {
      try {
        const res = await fetch(`${API_BASE}/content/${contentId}/status`, {
          headers: getAuthHeaders()
        });
        const data = await res.json();

        if (data.data?.status === 'completed') {
          setGeneratingContent(false);
          loadContents();
          loadContentDetail(contentId);
        } else if (data.data?.status === 'failed') {
          setGeneratingContent(false);
          alert('콘텐츠 생성에 실패했습니다.');
        } else {
          setTimeout(checkStatus, 2000);
        }
      } catch (error) {
        setGeneratingContent(false);
      }
    };
    checkStatus();
  };

  // Note functions
  const createNote = async () => {
    if (!noteTitle.trim()) return;

    try {
      const res = await fetch(`${API_BASE}/notes`, {
        method: 'POST',
        headers: getAuthHeaders(),
        body: JSON.stringify({
          title: noteTitle,
          content: noteContent,
          note_type: 'text',
          folder_id: selectedFolder,
          project_id: selectedProject?.id,
          tags: []
        })
      });

      if (res.ok) {
        setNoteTitle('');
        setNoteContent('');
        loadNotes();
      }
    } catch (error) {
      console.error('Failed to create note:', error);
    }
  };

  const saveAIResponse = async (messageId: string) => {
    const message = messages.find(m => m.id === messageId);
    if (!message) return;

    try {
      const res = await fetch(`${API_BASE}/notes`, {
        method: 'POST',
        headers: getAuthHeaders(),
        body: JSON.stringify({
          title: `AI 응답 - ${new Date().toLocaleDateString()}`,
          content: message.content,
          note_type: 'ai_response',
          folder_id: selectedFolder,
          project_id: selectedProject?.id,
          tags: ['ai-response'],
          source: 'ai_chat'
        })
      });

      if (res.ok) {
        alert('노트가 저장되었습니다.');
        loadNotes();
      }
    } catch (error) {
      console.error('Failed to save AI response:', error);
    }
  };

  // Project functions
  const createProject = async (name: string, description: string) => {
    try {
      const res = await fetch(`${API_BASE}/projects`, {
        method: 'POST',
        headers: getAuthHeaders(),
        body: JSON.stringify({
          name,
          description,
          visibility: 'private'
        })
      });

      if (res.ok) {
        loadProjects();
      }
    } catch (error) {
      console.error('Failed to create project:', error);
    }
  };

  // Search function
  const handleSearch = async () => {
    if (!searchQuery.trim()) return;

    try {
      const res = await fetch(`${API_BASE}/notes/search`, {
        method: 'POST',
        headers: getAuthHeaders(),
        body: JSON.stringify({
          query: searchQuery
        })
      });

      const data = await res.json();
      setSearchResults(data.data?.results || []);
    } catch (error) {
      console.error('Failed to search:', error);
    }
  };

  // Knowledge Graph functions
  const loadKnowledgeGraphs = async () => {
    try {
      const res = await fetch(`${API_BASE}/knowledge-graph?page=1&limit=50`, {
        headers: getAuthHeaders()
      });
      const data = await res.json();
      setKnowledgeGraphs(data.data?.knowledge_graphs || []);
    } catch (error) {
      console.error('Failed to load knowledge graphs:', error);
    }
  };

  const buildKnowledgeGraph = async () => {
    if (!kgQuery.trim()) return;

    setBuildingKG(true);
    setKgAnswer(null);

    try {
      const res = await fetch(`${API_BASE}/knowledge-graph/build`, {
        method: 'POST',
        headers: getAuthHeaders(),
        body: JSON.stringify({
          query: kgQuery,
          document_ids: selectedDocuments,
          name: `KG: ${kgQuery.substring(0, 50)}`,
          max_entities: 50,
          max_relationships: 100,
          use_llm_extraction: true,
          infer_relationships: true
        })
      });

      const data = await res.json();
      if (data.data?.knowledge_graph) {
        setSelectedKG(data.data.knowledge_graph);
        loadKnowledgeGraphs();
      }
    } catch (error) {
      console.error('Failed to build knowledge graph:', error);
    } finally {
      setBuildingKG(false);
    }
  };

  const queryKnowledgeGraph = async () => {
    if (!selectedKG || !kgQuery.trim()) return;

    setQueryingKG(true);
    setKgAnswer(null);

    try {
      const res = await fetch(`${API_BASE}/knowledge-graph/${selectedKG.id}/query`, {
        method: 'POST',
        headers: getAuthHeaders(),
        body: JSON.stringify({
          query: kgQuery,
          max_hops: 3,
          include_paths: true
        })
      });

      const data = await res.json();
      if (data.data?.answer) {
        setKgAnswer(data.data.answer);
      }
    } catch (error) {
      console.error('Failed to query knowledge graph:', error);
    } finally {
      setQueryingKG(false);
    }
  };

  const deleteKnowledgeGraph = async (kgId: string) => {
    if (!confirm('정말 이 Knowledge Graph를 삭제하시겠습니까?')) return;

    try {
      await fetch(`${API_BASE}/knowledge-graph/${kgId}`, {
        method: 'DELETE',
        headers: getAuthHeaders()
      });

      if (selectedKG?.id === kgId) {
        setSelectedKG(null);
      }
      loadKnowledgeGraphs();
    } catch (error) {
      console.error('Failed to delete knowledge graph:', error);
    }
  };

  // Get entity type color for visualization
  const getEntityColor = (entityType: string): string => {
    const colors: Record<string, string> = {
      concept: '#4A90D9',
      person: '#E74C3C',
      organization: '#2ECC71',
      location: '#F39C12',
      technology: '#9B59B6',
      event: '#E91E63',
      document: '#00BCD4',
      topic: '#FF5722',
      process: '#795548',
      product: '#607D8B',
      term: '#3F51B5',
      metric: '#009688',
      date: '#FF9800',
      quantity: '#8BC34A'
    };
    return colors[entityType] || '#6C757D';
  };

  // Knowledge Article functions
  const loadKnowledgeArticles = async () => {
    try {
      const res = await fetch(`${API_BASE}/knowledge?status=published&page=1&limit=50`, {
        headers: getAuthHeaders()
      });
      const data = await res.json();
      setKnowledgeArticles(data.data?.articles || []);
    } catch (error) {
      console.error('Failed to load knowledge articles:', error);
    }
  };

  const loadCategories = async () => {
    try {
      const res = await fetch(`${API_BASE}/knowledge/categories?language=${articleLanguage}`, {
        headers: getAuthHeaders()
      });
      const data = await res.json();
      setCategories(data.data?.categories || []);
    } catch (error) {
      console.error('Failed to load categories:', error);
    }
  };

  const loadTopContributors = async () => {
    try {
      const res = await fetch(`${API_BASE}/knowledge/top-contributors?limit=10`, {
        headers: getAuthHeaders()
      });
      const data = await res.json();
      setTopContributors(data.data?.contributors || []);
    } catch (error) {
      console.error('Failed to load top contributors:', error);
    }
  };

  const loadPendingReviews = async () => {
    try {
      const res = await fetch(`${API_BASE}/knowledge/pending-reviews?page=1&limit=20`, {
        headers: getAuthHeaders()
      });
      const data = await res.json();
      setPendingReviews(data.data?.articles || []);
    } catch (error) {
      console.error('Failed to load pending reviews:', error);
    }
  };

  const createKnowledgeArticle = async () => {
    if (!newArticle.title.trim() || !newArticle.content.trim()) return;

    setSavingArticle(true);
    try {
      const res = await fetch(`${API_BASE}/knowledge`, {
        method: 'POST',
        headers: getAuthHeaders(),
        body: JSON.stringify({
          title: newArticle.title,
          content: newArticle.content,
          summary: newArticle.summary,
          category: newArticle.category,
          tags: newArticle.tags,
          primary_language: 'ko'
        })
      });

      const data = await res.json();
      if (data.status === 'success') {
        setShowCreateArticle(false);
        setNewArticle({ title: '', content: '', summary: '', category: 'technical', tags: [] });
        loadKnowledgeArticles();
      }
    } catch (error) {
      console.error('Failed to create knowledge article:', error);
    } finally {
      setSavingArticle(false);
    }
  };

  const submitForReview = async (articleId: string) => {
    try {
      const res = await fetch(`${API_BASE}/knowledge/${articleId}/submit`, {
        method: 'POST',
        headers: getAuthHeaders()
      });

      const data = await res.json();
      if (data.status === 'success') {
        alert(data.message || '검수 요청되었습니다.');
        loadKnowledgeArticles();
      }
    } catch (error) {
      console.error('Failed to submit for review:', error);
    }
  };

  const reviewArticle = async (articleId: string, action: 'approve' | 'reject' | 'request_changes') => {
    if (!reviewComment.trim()) {
      alert('검수 코멘트를 입력해주세요.');
      return;
    }

    try {
      const res = await fetch(`${API_BASE}/knowledge/${articleId}/review`, {
        method: 'POST',
        headers: getAuthHeaders(),
        body: JSON.stringify({
          action,
          comment: reviewComment
        })
      });

      const data = await res.json();
      if (data.status === 'success') {
        alert(data.message || '검수가 완료되었습니다.');
        setReviewComment('');
        setSelectedArticle(null);
        loadPendingReviews();
        loadKnowledgeArticles();
      }
    } catch (error) {
      console.error('Failed to review article:', error);
    }
  };

  const recommendArticle = async (articleId: string) => {
    try {
      const res = await fetch(`${API_BASE}/knowledge/${articleId}/recommend`, {
        method: 'POST',
        headers: getAuthHeaders()
      });

      const data = await res.json();
      if (data.status === 'success') {
        // Update local state
        setKnowledgeArticles(prev => prev.map(a =>
          a.id === articleId
            ? { ...a, recommendation_count: data.data.recommendation_count }
            : a
        ));
        if (selectedArticle?.id === articleId) {
          setSelectedArticle(prev => prev ? { ...prev, recommendation_count: data.data.recommendation_count } : null);
        }
      }
    } catch (error) {
      console.error('Failed to recommend article:', error);
    }
  };

  // Notification functions
  const loadNotifications = async () => {
    try {
      const res = await fetch(`${API_BASE}/notifications?page=1&limit=20`, {
        headers: getAuthHeaders()
      });
      const data = await res.json();
      setNotifications(data.data?.notifications || []);
    } catch (error) {
      console.error('Failed to load notifications:', error);
    }
  };

  const loadUnreadCount = async () => {
    try {
      const res = await fetch(`${API_BASE}/notifications/count`, {
        headers: getAuthHeaders()
      });
      const data = await res.json();
      setUnreadCount(data.data?.total || 0);
    } catch (error) {
      console.error('Failed to load unread count:', error);
    }
  };

  const markNotificationAsRead = async (notificationIds: string[]) => {
    try {
      await fetch(`${API_BASE}/notifications/read`, {
        method: 'POST',
        headers: getAuthHeaders(),
        body: JSON.stringify({ notification_ids: notificationIds })
      });
      loadNotifications();
      loadUnreadCount();
    } catch (error) {
      console.error('Failed to mark notification as read:', error);
    }
  };

  const markAllNotificationsAsRead = async () => {
    try {
      await fetch(`${API_BASE}/notifications/read-all`, {
        method: 'POST',
        headers: getAuthHeaders()
      });
      loadNotifications();
      loadUnreadCount();
    } catch (error) {
      console.error('Failed to mark all notifications as read:', error);
    }
  };

  // Get status badge color
  const getStatusColor = (status: KnowledgeStatus): string => {
    const colors: Record<KnowledgeStatus, string> = {
      draft: '#6C757D',
      pending: '#F39C12',
      in_review: '#3498DB',
      approved: '#2ECC71',
      rejected: '#E74C3C',
      published: '#27AE60'
    };
    return colors[status] || '#6C757D';
  };

  const getStatusLabel = (status: KnowledgeStatus): string => {
    const labels: Record<KnowledgeStatus, string> = {
      draft: '작성 중',
      pending: '검수 대기',
      in_review: '검수 중',
      approved: '승인됨',
      rejected: '반려됨',
      published: '게시됨'
    };
    return labels[status] || status;
  };

  // Upload document
  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) {
      setUploadFile(file);
    }
  };

  const uploadDocument = async () => {
    if (!uploadFile) return;

    setUploading(true);
    setUploadProgress('Uploading...');

    try {
      const formData = new FormData();
      formData.append('file', uploadFile);
      formData.append('processing_mode', uploadSettings.processingMode);
      formData.append('enable_vlm', String(uploadSettings.enableVLM));
      formData.append('extract_tables', String(uploadSettings.extractTables));
      formData.append('extract_images', String(uploadSettings.extractImages));
      formData.append('language', uploadSettings.language);

      const token = localStorage.getItem('access_token');
      const res = await fetch(`${API_BASE}/documents`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`
        },
        body: formData
      });

      const data = await res.json();

      if (res.ok) {
        setUploadProgress('Processing document...');
        // Poll for status
        pollUploadStatus(data.data.task_id);
      } else {
        setUploadProgress(`Error: ${data.detail?.message || 'Upload failed'}`);
        setTimeout(() => {
          setUploadProgress(null);
          setUploading(false);
        }, 3000);
      }
    } catch (error) {
      console.error('Upload failed:', error);
      setUploadProgress('Upload failed');
      setTimeout(() => {
        setUploadProgress(null);
        setUploading(false);
      }, 3000);
    }
  };

  const pollUploadStatus = async (taskId: string) => {
    const checkStatus = async () => {
      try {
        const res = await fetch(`${API_BASE}/documents/upload-status/${taskId}`, {
          headers: getAuthHeaders()
        });
        const data = await res.json();

        if (data.data?.status === 'ready') {
          setUploadProgress('Document processed successfully!');
          setShowUploadModal(false);
          setUploadFile(null);
          loadDocuments();
          setTimeout(() => {
            setUploadProgress(null);
            setUploading(false);
          }, 2000);
        } else if (data.data?.status === 'error') {
          setUploadProgress('Processing failed');
          setTimeout(() => {
            setUploadProgress(null);
            setUploading(false);
          }, 3000);
        } else {
          const progress = data.data?.progress?.overall_progress || 0;
          const step = data.data?.progress?.current_step || 'processing';
          setUploadProgress(`${step}... ${progress}%`);
          setTimeout(checkStatus, 1500);
        }
      } catch {
        setTimeout(checkStatus, 2000);
      }
    };
    checkStatus();
  };

  // Theme toggle
  const toggleTheme = () => {
    setTheme(prev => prev === 'dark' ? 'light' : 'dark');
  };

  // Styles
  const themeColors = theme === 'dark' ? {
    bg: 'linear-gradient(135deg, #0f0f23 0%, #1a1a2e 50%, #16213e 100%)',
    cardBg: 'rgba(255,255,255,0.05)',
    cardBorder: 'rgba(255,255,255,0.1)',
    text: '#fff',
    textSecondary: 'rgba(255,255,255,0.7)',
    accent: '#4A90D9',
    accentHover: '#357ABD'
  } : {
    bg: 'linear-gradient(135deg, #f5f7fa 0%, #e4e9f2 50%, #d3dce6 100%)',
    cardBg: 'rgba(255,255,255,0.8)',
    cardBorder: 'rgba(0,0,0,0.1)',
    text: '#1a1a2e',
    textSecondary: 'rgba(0,0,0,0.6)',
    accent: '#4A90D9',
    accentHover: '#357ABD'
  };

  const cardStyle: React.CSSProperties = {
    background: themeColors.cardBg,
    backdropFilter: 'blur(20px)',
    border: `1px solid ${themeColors.cardBorder}`,
    borderRadius: '16px',
    padding: '20px'
  };

  const tabStyle = (isActive: boolean): React.CSSProperties => ({
    padding: '12px 24px',
    border: 'none',
    background: isActive ? themeColors.accent : 'transparent',
    color: isActive ? '#fff' : themeColors.textSecondary,
    borderRadius: '8px',
    cursor: 'pointer',
    fontWeight: isActive ? 600 : 400,
    transition: 'all 0.2s'
  });

  return (
    <div style={{
      minHeight: '100vh',
      background: themeColors.bg,
      color: themeColors.text,
      display: 'flex'
    }}>
      {/* Sidebar */}
      <motion.aside
        initial={{ width: 280 }}
        animate={{ width: sidebarCollapsed ? 60 : 280 }}
        style={{
          ...cardStyle,
          borderRadius: 0,
          height: '100vh',
          display: 'flex',
          flexDirection: 'column',
          gap: '16px',
          overflowY: 'auto',
          overflowX: 'hidden'
        }}
      >
        {/* Logo & Toggle */}
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '8px 0' }}>
          {!sidebarCollapsed && <h1 style={{ fontSize: '20px', fontWeight: 700 }}>KMS</h1>}
          <button
            onClick={() => setSidebarCollapsed(!sidebarCollapsed)}
            style={{ background: 'transparent', border: 'none', color: themeColors.text, cursor: 'pointer', fontSize: '20px' }}
          >
            {sidebarCollapsed ? '>' : '<'}
          </button>
        </div>

        {/* User Info with Notification Bell */}
        {!sidebarCollapsed && (
          <div style={{ padding: '12px', background: 'rgba(255,255,255,0.05)', borderRadius: '8px' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <div>
                <div style={{ fontWeight: 600 }}>{user?.username || 'User'}</div>
                <div style={{ fontSize: '12px', color: themeColors.textSecondary }}>{user?.email}</div>
              </div>
              <div style={{ position: 'relative' }}>
                <button
                  onClick={() => setShowNotifications(!showNotifications)}
                  style={{
                    background: 'transparent',
                    border: 'none',
                    cursor: 'pointer',
                    fontSize: '20px',
                    position: 'relative'
                  }}
                >
                  🔔
                  {unreadCount > 0 && (
                    <span style={{
                      position: 'absolute',
                      top: '-5px',
                      right: '-5px',
                      background: '#E74C3C',
                      color: 'white',
                      borderRadius: '50%',
                      width: '18px',
                      height: '18px',
                      fontSize: '10px',
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center'
                    }}>
                      {unreadCount > 9 ? '9+' : unreadCount}
                    </span>
                  )}
                </button>
                {/* Notification Dropdown */}
                {showNotifications && (
                  <div style={{
                    position: 'absolute',
                    top: '100%',
                    right: 0,
                    marginTop: '8px',
                    width: '300px',
                    maxHeight: '400px',
                    overflow: 'auto',
                    background: themeColors.cardBg,
                    border: `1px solid ${themeColors.cardBorder}`,
                    borderRadius: '8px',
                    boxShadow: '0 4px 12px rgba(0,0,0,0.3)',
                    zIndex: 1000
                  }}>
                    <div style={{ padding: '12px', borderBottom: `1px solid ${themeColors.cardBorder}`, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                      <span style={{ fontWeight: 600 }}>{t('knowledge.notifications.title')}</span>
                      {unreadCount > 0 && (
                        <button
                          onClick={markAllNotificationsAsRead}
                          style={{ background: 'transparent', border: 'none', color: themeColors.accent, cursor: 'pointer', fontSize: '12px' }}
                        >
                          {t('knowledge.notifications.markAllRead')}
                        </button>
                      )}
                    </div>
                    {notifications.length === 0 ? (
                      <div style={{ padding: '20px', textAlign: 'center', color: themeColors.textSecondary }}>
                        {t('knowledge.notifications.empty')}
                      </div>
                    ) : (
                      notifications.map(notif => (
                        <div
                          key={notif.id}
                          onClick={() => {
                            if (!notif.is_read) markNotificationAsRead([notif.id]);
                            if (notif.reference_type === 'knowledge' && notif.reference_id) {
                              setActiveTab('knowledge-articles');
                            }
                            setShowNotifications(false);
                          }}
                          style={{
                            padding: '12px',
                            borderBottom: `1px solid ${themeColors.cardBorder}`,
                            cursor: 'pointer',
                            background: notif.is_read ? 'transparent' : 'rgba(74,144,217,0.1)'
                          }}
                        >
                          <div style={{ fontWeight: notif.is_read ? 400 : 600, fontSize: '13px' }}>{notif.title}</div>
                          <div style={{ fontSize: '12px', color: themeColors.textSecondary, marginTop: '4px' }}>{notif.message}</div>
                        </div>
                      ))
                    )}
                  </div>
                )}
              </div>
            </div>
          </div>
        )}

        {/* Navigation Tabs */}
        <nav style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
          {[
            { key: 'chat', labelKey: 'knowledge.sidebar.chat', icon: '💬' },
            { key: 'documents', labelKey: 'knowledge.sidebar.documents', icon: '📄' },
            { key: 'web-sources', labelKey: 'knowledge.sidebar.webSources', icon: '🌐' },
            { key: 'notes', labelKey: 'knowledge.sidebar.notes', icon: '📝' },
            { key: 'content', labelKey: 'knowledge.sidebar.aiContent', icon: '🤖' },
            { key: 'projects', labelKey: 'knowledge.sidebar.projects', icon: '📁' },
            { key: 'mindmap', labelKey: 'knowledge.sidebar.mindmap', icon: '🧠' },
            { key: 'knowledge-graph', labelKey: 'knowledge.sidebar.knowledgeGraph', icon: '🔗' },
            { key: 'knowledge-articles', labelKey: 'knowledge.sidebar.knowledgeBase', icon: '📚' }
          ].map(tab => (
            <button
              key={tab.key}
              onClick={() => {
                if (tab.key === 'mindmap') {
                  navigate('/mindmap');
                } else {
                  setActiveTab(tab.key as TabType);
                }
              }}
              style={{
                ...tabStyle(activeTab === tab.key),
                display: 'flex',
                alignItems: 'center',
                gap: '12px',
                justifyContent: sidebarCollapsed ? 'center' : 'flex-start'
              }}
            >
              <span>{tab.icon}</span>
              {!sidebarCollapsed && <span>{t(tab.labelKey as keyof import('../i18n/types').TranslationKeys)}</span>}
            </button>
          ))}
        </nav>

        {/* Projects List */}
        {!sidebarCollapsed && activeTab !== 'projects' && (
          <div style={{ flex: 1, overflow: 'auto' }}>
            <h3 style={{ fontSize: '14px', color: themeColors.textSecondary, marginBottom: '8px' }}>{t('knowledge.sidebar.projects')}</h3>
            {projects.map(project => (
              <div
                key={project.id}
                onClick={() => setSelectedProject(selectedProject?.id === project.id ? null : project)}
                style={{
                  padding: '10px',
                  borderRadius: '8px',
                  cursor: 'pointer',
                  background: selectedProject?.id === project.id ? 'rgba(74,144,217,0.2)' : 'transparent',
                  marginBottom: '4px'
                }}
              >
                <div style={{ fontWeight: 500 }}>{project.name}</div>
                <div style={{ fontSize: '12px', color: themeColors.textSecondary }}>
                  {project.document_count} docs
                </div>
              </div>
            ))}
          </div>
        )}

        {/* Bottom Actions */}
        <div style={{ marginTop: 'auto', display: 'flex', flexDirection: 'column', gap: '8px' }}>
          <button
            onClick={toggleTheme}
            style={{ ...tabStyle(false), display: 'flex', alignItems: 'center', gap: '12px', justifyContent: sidebarCollapsed ? 'center' : 'flex-start' }}
          >
            <span>{theme === 'dark' ? '🌙' : '☀️'}</span>
            {!sidebarCollapsed && <span>{theme === 'dark' ? t('knowledge.sidebar.dark') : t('knowledge.sidebar.light')}</span>}
          </button>
          {user?.role === 'admin' && (
            <button
              onClick={() => navigate('/admin')}
              style={{ ...tabStyle(false), display: 'flex', alignItems: 'center', gap: '12px', justifyContent: sidebarCollapsed ? 'center' : 'flex-start' }}
            >
              <span>👤</span>
              {!sidebarCollapsed && <span>{t('knowledge.sidebar.admin')}</span>}
            </button>
          )}
          <button
            onClick={logout}
            style={{ ...tabStyle(false), display: 'flex', alignItems: 'center', gap: '12px', justifyContent: sidebarCollapsed ? 'center' : 'flex-start' }}
          >
            <span>🚪</span>
            {!sidebarCollapsed && <span>{t('knowledge.sidebar.logout')}</span>}
          </button>
          <button
            onClick={() => setShowSettingsPopup(true)}
            style={{ ...tabStyle(false), display: 'flex', alignItems: 'center', gap: '12px', justifyContent: sidebarCollapsed ? 'center' : 'flex-start' }}
          >
            <span>⚙️</span>
            {!sidebarCollapsed && <span>{t('knowledge.sidebar.settings')}</span>}
          </button>
        </div>
      </motion.aside>

      {/* Settings Popup */}
      <AnimatePresence>
        {showSettingsPopup && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            onClick={() => setShowSettingsPopup(false)}
            style={{
              position: 'fixed',
              top: 0,
              left: 0,
              right: 0,
              bottom: 0,
              background: 'rgba(0, 0, 0, 0.5)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              zIndex: 2000
            }}
          >
            <motion.div
              initial={{ scale: 0.9, opacity: 0 }}
              animate={{ scale: 1, opacity: 1 }}
              exit={{ scale: 0.9, opacity: 0 }}
              onClick={(e) => e.stopPropagation()}
              style={{
                ...cardStyle,
                width: '400px',
                maxWidth: '90vw',
                padding: '24px'
              }}
            >
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '24px' }}>
                <h2 style={{ margin: 0, fontSize: '20px', fontWeight: 600 }}>{t('knowledge.sidebar.settings')}</h2>
                <button
                  onClick={() => setShowSettingsPopup(false)}
                  style={{
                    background: 'transparent',
                    border: 'none',
                    color: themeColors.text,
                    fontSize: '24px',
                    cursor: 'pointer',
                    padding: '4px'
                  }}
                >
                  ×
                </button>
              </div>

              {/* Language Settings */}
              <div style={{ marginBottom: '16px' }}>
                <label style={{ display: 'block', marginBottom: '8px', fontWeight: 500, color: themeColors.textSecondary }}>
                  Language / 언어 / 言語
                </label>
                <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                  {(['en', 'ko', 'ja'] as LanguageCode[]).map((lang) => {
                    const langInfo = LANGUAGES[lang];
                    const isSelected = language === lang;
                    return (
                      <button
                        key={lang}
                        onClick={() => setLanguage(lang)}
                        style={{
                          display: 'flex',
                          alignItems: 'center',
                          gap: '12px',
                          padding: '12px 16px',
                          background: isSelected ? themeColors.accent : 'rgba(255, 255, 255, 0.05)',
                          border: isSelected ? `2px solid ${themeColors.accent}` : '2px solid transparent',
                          borderRadius: '8px',
                          color: isSelected ? '#fff' : themeColors.text,
                          cursor: 'pointer',
                          transition: 'all 0.2s',
                          textAlign: 'left'
                        }}
                      >
                        <span style={{ fontSize: '24px' }}>{langInfo.flag}</span>
                        <div>
                          <div style={{ fontWeight: 500 }}>{langInfo.nativeName}</div>
                          <div style={{ fontSize: '12px', opacity: 0.7 }}>{langInfo.name}</div>
                        </div>
                        {isSelected && (
                          <span style={{ marginLeft: 'auto', fontSize: '18px' }}>✓</span>
                        )}
                      </button>
                    );
                  })}
                </div>
              </div>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Main Content */}
      <main style={{ flex: 1, padding: '24px', overflow: 'auto', display: 'flex', gap: '24px' }}>
        <AnimatePresence mode="wait">
          {/* Chat Tab */}
          {activeTab === 'chat' && (
            <motion.div
              key="chat"
              initial={{ opacity: 0, x: 20 }}
              animate={{ opacity: 1, x: 0 }}
              exit={{ opacity: 0, x: -20 }}
              style={{ flex: 1, display: 'flex', flexDirection: 'column', gap: '16px' }}
            >
              {/* Chat Header */}
              <div style={cardStyle}>
                <h2 style={{ margin: 0 }}>{t('knowledge.chat.title')}</h2>
                <p style={{ color: themeColors.textSecondary, margin: '8px 0 0' }}>
                  {t('knowledge.chat.subtitle', { count: selectedDocuments.length })}
                </p>
              </div>

              {/* Messages */}
              <div style={{ ...cardStyle, flex: 1, overflow: 'auto', display: 'flex', flexDirection: 'column', gap: '16px' }}>
                {messages.length === 0 ? (
                  <div style={{ textAlign: 'center', padding: '40px', color: themeColors.textSecondary }}>
                    <p>{t('knowledge.chat.startPrompt')}</p>
                    <div style={{ display: 'flex', flexWrap: 'wrap', gap: '8px', justifyContent: 'center', marginTop: '16px' }}>
                      {[
                        { key: 'summarize', label: t('knowledge.chat.quickPrompts.summarize') },
                        { key: 'keyConcepts', label: t('knowledge.chat.quickPrompts.keyConcepts') },
                        { key: 'showExamples', label: t('knowledge.chat.quickPrompts.showExamples') }
                      ].map((q) => (
                        <button
                          key={q.key}
                          onClick={() => setInputMessage(q.label)}
                          style={{ ...tabStyle(false), fontSize: '14px' }}
                        >
                          {q.label}
                        </button>
                      ))}
                    </div>
                  </div>
                ) : (
                  messages.map(msg => (
                    <div
                      key={msg.id}
                      style={{
                        alignSelf: msg.role === 'user' ? 'flex-end' : 'flex-start',
                        maxWidth: '80%',
                        background: msg.role === 'user' ? themeColors.accent : 'rgba(255,255,255,0.1)',
                        padding: '12px 16px',
                        borderRadius: '12px'
                      }}
                    >
                      <div style={{ whiteSpace: 'pre-wrap' }}>{msg.content}</div>

                      {/* Sources (Citations) */}
                      {msg.sources && msg.sources.length > 0 && (
                        <div style={{ marginTop: '12px', fontSize: '12px' }}>
                          <div style={{ color: themeColors.textSecondary, marginBottom: '8px' }}>
                            {t('knowledge.sources')} ({msg.sources.length}):
                          </div>
                          {msg.sources.map((source, idx) => (
                            <div
                              key={idx}
                              onClick={() => {
                                setSelectedSource(source);
                                setShowSourcePanel(true);
                              }}
                              style={{
                                padding: '8px',
                                background: 'rgba(74,144,217,0.2)',
                                borderRadius: '6px',
                                marginBottom: '4px',
                                cursor: 'pointer'
                              }}
                            >
                              <span style={{ fontWeight: 600 }}>[{idx + 1}]</span> {source.doc_name} (신뢰도: {(source.score * 100).toFixed(0)}%)
                            </div>
                          ))}
                        </div>
                      )}

                      {/* Save to note button */}
                      {msg.role === 'assistant' && (
                        <button
                          onClick={() => saveAIResponse(msg.id)}
                          style={{ ...tabStyle(false), fontSize: '12px', marginTop: '8px' }}
                        >
                          📝 노트로 저장
                        </button>
                      )}
                    </div>
                  ))
                )}

                {isLoading && (
                  <div style={{ alignSelf: 'flex-start', padding: '12px 16px', background: 'rgba(255,255,255,0.1)', borderRadius: '12px' }}>
                    <span className="loading">응답 생성 중...</span>
                  </div>
                )}
              </div>

              {/* Suggested Questions */}
              {suggestedQuestions.length > 0 && (
                <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap' }}>
                  {suggestedQuestions.map((q, i) => (
                    <button
                      key={i}
                      onClick={() => setInputMessage(q)}
                      style={{ ...tabStyle(false), fontSize: '12px' }}
                    >
                      {q}
                    </button>
                  ))}
                </div>
              )}

              {/* Session Documents */}
              {sessionDocuments.length > 0 && (
                <div style={{
                  ...cardStyle,
                  background: 'rgba(46, 204, 113, 0.1)',
                  border: '1px solid rgba(46, 204, 113, 0.3)',
                  padding: '12px'
                }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '8px' }}>
                    <span style={{ fontSize: '14px' }}>📎 현재 대화에서 사용 중인 문서</span>
                    <span style={{
                      fontSize: '11px',
                      padding: '2px 6px',
                      background: 'rgba(46, 204, 113, 0.3)',
                      borderRadius: '4px',
                      color: '#2ECC71'
                    }}>
                      우선 참조
                    </span>
                  </div>
                  <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap' }}>
                    {sessionDocuments.map(doc => (
                      <div
                        key={doc.id}
                        style={{
                          display: 'flex',
                          alignItems: 'center',
                          gap: '8px',
                          padding: '6px 10px',
                          background: 'rgba(255,255,255,0.1)',
                          borderRadius: '6px',
                          fontSize: '12px'
                        }}
                      >
                        <span>{doc.filename}</span>
                        {doc.status === 'processing' && (
                          <span style={{ color: '#F1C40F' }}>처리중...</span>
                        )}
                        {doc.status === 'ready' && (
                          <span style={{ color: '#2ECC71' }}>({doc.chunk_count} chunks)</span>
                        )}
                        {doc.status === 'error' && (
                          <span style={{ color: '#E74C3C' }}>오류</span>
                        )}
                        <button
                          onClick={() => removeSessionDocument(doc.id)}
                          style={{
                            background: 'none',
                            border: 'none',
                            color: '#E74C3C',
                            cursor: 'pointer',
                            padding: '2px 4px',
                            fontSize: '14px'
                          }}
                        >
                          ×
                        </button>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Input with File Upload */}
              <div
                style={{
                  ...cardStyle,
                  display: 'flex',
                  flexDirection: 'column',
                  gap: '12px',
                  border: dragOver ? `2px dashed ${themeColors.accent}` : undefined,
                  background: dragOver ? 'rgba(74, 144, 217, 0.1)' : undefined
                }}
                onDragOver={handleDragOver}
                onDragLeave={handleDragLeave}
                onDrop={handleDrop}
              >
                {/* External Resources Indicator */}
                {externalConnections.filter(c => c.status === 'connected').length > 0 && (
                  <div style={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: '8px',
                    padding: '8px 12px',
                    background: 'rgba(46, 204, 113, 0.1)',
                    borderRadius: '6px',
                    fontSize: '12px',
                    color: '#2ECC71',
                    marginBottom: '4px'
                  }}>
                    🔗 {t('knowledge.external.connectedStatus' as keyof import('../i18n/types').TranslationKeys)}:
                    {externalConnections.filter(c => c.status === 'connected').map(conn => {
                      const resource = availableResources.find(r => r.type === conn.resource_type);
                      return (
                        <span key={conn.id} style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
                          {resource?.icon} {t(`knowledge.external.resources.${resource?.type === 'google_drive' ? 'googleDrive' : resource?.type}.name` as keyof import('../i18n/types').TranslationKeys)} ({conn.document_count})
                        </span>
                      );
                    })}
                  </div>
                )}

                {/* Upload Buttons */}
                <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap' }}>
                  {/* + Button for External Resources */}
                  <button
                    onClick={() => setShowExternalModal(true)}
                    style={{
                      padding: '8px 12px',
                      fontSize: '14px',
                      fontWeight: 'bold',
                      display: 'flex',
                      alignItems: 'center',
                      gap: '4px',
                      borderRadius: '8px',
                      cursor: 'pointer',
                      transition: 'all 0.2s',
                      background: externalConnections.some(c => c.status === 'connected')
                        ? 'rgba(46, 204, 113, 0.2)'
                        : 'rgba(74, 144, 217, 0.15)',
                      border: externalConnections.some(c => c.status === 'connected')
                        ? '1px solid #2ECC71'
                        : '1px solid rgba(74, 144, 217, 0.5)',
                      color: externalConnections.some(c => c.status === 'connected')
                        ? '#2ECC71'
                        : themeColors.accent
                    }}
                    title={t('knowledge.external.buttonTitle' as keyof import('../i18n/types').TranslationKeys)}
                  >
                    ➕ {t('knowledge.external.button' as keyof import('../i18n/types').TranslationKeys)}
                  </button>
                  <label style={{
                    ...tabStyle(false),
                    cursor: uploadingSessionDoc ? 'not-allowed' : 'pointer',
                    fontSize: '12px',
                    display: 'flex',
                    alignItems: 'center',
                    gap: '4px',
                    opacity: uploadingSessionDoc ? 0.5 : 1
                  }}>
                    📎 {t('knowledge.upload.fileAttach')}
                    <input
                      type="file"
                      style={{ display: 'none' }}
                      accept=".pdf,.txt,.md,.docx,.png,.jpg,.jpeg"
                      onChange={(e) => {
                        const file = e.target.files?.[0];
                        if (file) uploadSessionFile(file);
                        e.target.value = '';
                      }}
                      disabled={uploadingSessionDoc}
                    />
                  </label>
                  <button
                    onClick={() => setShowPasteModal(true)}
                    style={{ ...tabStyle(false), fontSize: '12px' }}
                    disabled={uploadingSessionDoc}
                  >
                    📝 {t('knowledge.upload.pasteText')}
                  </button>
                  {uploadingSessionDoc && (
                    <span style={{ color: themeColors.textSecondary, fontSize: '12px', alignSelf: 'center' }}>
                      처리 중...
                    </span>
                  )}
                </div>

                {/* Message Input */}
                <div style={{ display: 'flex', gap: '12px' }}>
                  <input
                    type="text"
                    value={inputMessage}
                    onChange={(e) => setInputMessage(e.target.value)}
                    onKeyPress={(e) => e.key === 'Enter' && sendMessage()}
                    placeholder={t('knowledge.chat.inputPlaceholder')}
                    style={{
                      flex: 1,
                      padding: '12px 16px',
                      background: 'rgba(255,255,255,0.1)',
                      border: `1px solid ${themeColors.cardBorder}`,
                      borderRadius: '8px',
                      color: themeColors.text,
                      fontSize: '16px'
                    }}
                  />
                  <button
                    onClick={sendMessage}
                    disabled={isLoading || !inputMessage.trim()}
                    style={{
                      padding: '12px 24px',
                      background: themeColors.accent,
                      color: '#fff',
                      border: 'none',
                      borderRadius: '8px',
                      cursor: isLoading ? 'not-allowed' : 'pointer',
                      opacity: isLoading || !inputMessage.trim() ? 0.5 : 1
                    }}
                  >
                    {t('knowledge.chat.send')}
                  </button>
                </div>
              </div>

              {/* Text Paste Modal */}
              <AnimatePresence>
                {showPasteModal && (
                  <motion.div
                    initial={{ opacity: 0 }}
                    animate={{ opacity: 1 }}
                    exit={{ opacity: 0 }}
                    style={{
                      position: 'fixed',
                      top: 0, left: 0, right: 0, bottom: 0,
                      background: 'rgba(0,0,0,0.7)',
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                      zIndex: 1000
                    }}
                    onClick={() => setShowPasteModal(false)}
                  >
                    <motion.div
                      initial={{ scale: 0.9, opacity: 0 }}
                      animate={{ scale: 1, opacity: 1 }}
                      exit={{ scale: 0.9, opacity: 0 }}
                      style={{ ...cardStyle, width: '600px', maxWidth: '90%' }}
                      onClick={e => e.stopPropagation()}
                    >
                      <h3 style={{ margin: '0 0 16px' }}>📝 {t('knowledge.upload.pasteText')}</h3>
                      <p style={{ color: themeColors.textSecondary, fontSize: '14px', marginBottom: '16px' }}>
                        문서 내용이나 참고자료를 붙여넣으면 현재 대화에서 우선적으로 참조합니다.
                      </p>

                      <input
                        type="text"
                        placeholder="제목 (선택)"
                        value={pasteTitle}
                        onChange={e => setPasteTitle(e.target.value)}
                        style={{
                          ...inputStyle,
                          width: '100%',
                          marginBottom: '12px'
                        }}
                      />

                      <textarea
                        placeholder="내용을 붙여넣으세요..."
                        value={pasteContent}
                        onChange={e => setPasteContent(e.target.value)}
                        style={{
                          ...inputStyle,
                          width: '100%',
                          minHeight: '200px',
                          resize: 'vertical',
                          fontFamily: 'inherit'
                        }}
                      />

                      <div style={{ display: 'flex', gap: '12px', marginTop: '20px' }}>
                        <button
                          onClick={() => setShowPasteModal(false)}
                          style={{ ...tabStyle(false), flex: 1 }}
                        >
                          취소
                        </button>
                        <button
                          onClick={pasteSessionText}
                          disabled={!pasteContent.trim() || uploadingSessionDoc}
                          style={{
                            ...tabStyle(true),
                            flex: 1,
                            opacity: !pasteContent.trim() || uploadingSessionDoc ? 0.5 : 1,
                            cursor: !pasteContent.trim() || uploadingSessionDoc ? 'not-allowed' : 'pointer'
                          }}
                        >
                          {uploadingSessionDoc ? '처리 중...' : '추가'}
                        </button>
                      </div>
                    </motion.div>
                  </motion.div>
                )}
              </AnimatePresence>

              {/* External Connection Modal */}
              <AnimatePresence>
                {showExternalModal && (
                  <motion.div
                    initial={{ opacity: 0 }}
                    animate={{ opacity: 1 }}
                    exit={{ opacity: 0 }}
                    style={{
                      position: 'fixed',
                      top: 0, left: 0, right: 0, bottom: 0,
                      background: 'rgba(0,0,0,0.7)',
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                      zIndex: 1000
                    }}
                    onClick={() => setShowExternalModal(false)}
                  >
                    <motion.div
                      initial={{ scale: 0.9, opacity: 0 }}
                      animate={{ scale: 1, opacity: 1 }}
                      exit={{ scale: 0.9, opacity: 0 }}
                      style={{ ...cardStyle, width: '600px', maxWidth: '90%', maxHeight: '80vh', overflow: 'auto' }}
                      onClick={e => e.stopPropagation()}
                    >
                      <h3 style={{ margin: '0 0 8px', display: 'flex', alignItems: 'center', gap: '8px' }}>
                        🔗 {t('knowledge.external.title' as keyof import('../i18n/types').TranslationKeys)}
                      </h3>
                      <p style={{ color: themeColors.textSecondary, fontSize: '14px', marginBottom: '20px' }}>
                        {t('knowledge.external.description' as keyof import('../i18n/types').TranslationKeys)}
                      </p>

                      {/* Connected Resources */}
                      {externalConnections.length > 0 && (
                        <div style={{ marginBottom: '24px' }}>
                          <h4 style={{ margin: '0 0 12px', fontSize: '14px', color: themeColors.textSecondary }}>
                            {t('knowledge.external.connectedResources' as keyof import('../i18n/types').TranslationKeys)}
                          </h4>
                          {externalConnections.map(conn => {
                            const resource = availableResources.find(r => r.type === conn.resource_type);
                            return (
                              <div key={conn.id} style={{
                                display: 'flex',
                                alignItems: 'center',
                                justifyContent: 'space-between',
                                padding: '12px',
                                background: 'rgba(255,255,255,0.05)',
                                borderRadius: '8px',
                                marginBottom: '8px'
                              }}>
                                <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                                  <span style={{ fontSize: '24px' }}>{resource?.icon}</span>
                                  <div>
                                    <div style={{ fontWeight: 500 }}>{resource?.name}</div>
                                    <div style={{ fontSize: '12px', color: themeColors.textSecondary }}>
                                      {conn.status === 'connected' ? (
                                        <span style={{ color: '#2ECC71' }}>
                                          ✓ {t('knowledge.external.connected' as keyof import('../i18n/types').TranslationKeys)} • {conn.document_count} {t('knowledge.external.documents' as keyof import('../i18n/types').TranslationKeys)} • {conn.chunk_count} {t('knowledge.external.chunks' as keyof import('../i18n/types').TranslationKeys)}
                                        </span>
                                      ) : conn.status === 'syncing' ? (
                                        <span style={{ color: '#F39C12' }}>{t('knowledge.external.syncing' as keyof import('../i18n/types').TranslationKeys)}</span>
                                      ) : conn.status === 'error' ? (
                                        <span style={{ color: '#E74C3C' }}>{t('knowledge.external.error' as keyof import('../i18n/types').TranslationKeys)}: {conn.error_message}</span>
                                      ) : (
                                        <span>{t('knowledge.external.waiting' as keyof import('../i18n/types').TranslationKeys)}</span>
                                      )}
                                    </div>
                                  </div>
                                </div>
                                <div style={{ display: 'flex', gap: '8px' }}>
                                  {conn.status === 'connected' && (
                                    <button
                                      onClick={() => syncExternalResource(conn.id)}
                                      disabled={syncingConnection === conn.id}
                                      style={{
                                        ...tabStyle(false),
                                        fontSize: '12px',
                                        padding: '6px 12px'
                                      }}
                                    >
                                      {syncingConnection === conn.id ? t('knowledge.external.syncing' as keyof import('../i18n/types').TranslationKeys) : `🔄 ${t('knowledge.external.syncButton' as keyof import('../i18n/types').TranslationKeys)}`}
                                    </button>
                                  )}
                                  <button
                                    onClick={() => disconnectExternalResource(conn.id)}
                                    style={{
                                      ...tabStyle(false),
                                      fontSize: '12px',
                                      padding: '6px 12px',
                                      color: '#E74C3C',
                                      borderColor: '#E74C3C'
                                    }}
                                  >
                                    {t('knowledge.external.disconnect' as keyof import('../i18n/types').TranslationKeys)}
                                  </button>
                                </div>
                              </div>
                            );
                          })}
                        </div>
                      )}

                      {/* Available Resources */}
                      <h4 style={{ margin: '0 0 12px', fontSize: '14px', color: themeColors.textSecondary }}>
                        {t('knowledge.external.availableResources' as keyof import('../i18n/types').TranslationKeys)}
                      </h4>
                      <div style={{ display: 'grid', gap: '12px' }}>
                        {availableResources.map(resource => {
                          const isConnected = externalConnections.some(
                            c => c.resource_type === resource.type && c.status === 'connected'
                          );
                          const isConnecting = connectingResource === resource.type;

                          return (
                            <div key={resource.type} style={{
                              display: 'flex',
                              alignItems: 'center',
                              justifyContent: 'space-between',
                              padding: '16px',
                              background: isConnected ? 'rgba(46, 204, 113, 0.1)' : 'rgba(255,255,255,0.05)',
                              borderRadius: '8px',
                              border: isConnected ? '1px solid rgba(46, 204, 113, 0.3)' : '1px solid transparent'
                            }}>
                              <div style={{ display: 'flex', alignItems: 'center', gap: '16px' }}>
                                <span style={{ fontSize: '32px' }}>{resource.icon}</span>
                                <div>
                                  <div style={{ fontWeight: 600, fontSize: '16px' }}>
                                    {t(`knowledge.external.resources.${resource.type === 'google_drive' ? 'googleDrive' : resource.type}.name` as keyof import('../i18n/types').TranslationKeys)}
                                  </div>
                                  <div style={{ fontSize: '13px', color: themeColors.textSecondary }}>
                                    {t(`knowledge.external.resources.${resource.type === 'google_drive' ? 'googleDrive' : resource.type}.description` as keyof import('../i18n/types').TranslationKeys)}
                                  </div>
                                  <div style={{
                                    fontSize: '11px',
                                    color: themeColors.textSecondary,
                                    marginTop: '4px'
                                  }}>
                                    {resource.authType === 'oauth2' ? `🔐 ${t('knowledge.external.oauthAuth' as keyof import('../i18n/types').TranslationKeys)}` : `🔑 ${t('knowledge.external.apiToken' as keyof import('../i18n/types').TranslationKeys)}`}
                                  </div>
                                </div>
                              </div>
                              <button
                                onClick={() => !isConnected && connectExternalResource(resource.type)}
                                disabled={isConnected || isConnecting}
                                style={{
                                  ...tabStyle(false),
                                  padding: '10px 20px',
                                  opacity: isConnected ? 0.5 : 1,
                                  cursor: isConnected ? 'not-allowed' : 'pointer',
                                  background: isConnected ? 'rgba(46, 204, 113, 0.2)' : undefined
                                }}
                              >
                                {isConnected ? `✓ ${t('knowledge.external.connected' as keyof import('../i18n/types').TranslationKeys)}` : isConnecting ? t('knowledge.external.connecting' as keyof import('../i18n/types').TranslationKeys) : t('knowledge.external.connect' as keyof import('../i18n/types').TranslationKeys)}
                              </button>
                            </div>
                          );
                        })}
                      </div>

                      <div style={{ display: 'flex', justifyContent: 'flex-end', marginTop: '24px' }}>
                        <button
                          onClick={() => setShowExternalModal(false)}
                          style={{ ...tabStyle(false) }}
                        >
                          {t('knowledge.external.close' as keyof import('../i18n/types').TranslationKeys)}
                        </button>
                      </div>
                    </motion.div>
                  </motion.div>
                )}
              </AnimatePresence>
            </motion.div>
          )}

          {/* Documents Tab */}
          {activeTab === 'documents' && (
            <motion.div
              key="documents"
              initial={{ opacity: 0, x: 20 }}
              animate={{ opacity: 1, x: 0 }}
              exit={{ opacity: 0, x: -20 }}
              style={{ flex: 1 }}
            >
              <div style={cardStyle}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' }}>
                  <div>
                    <h2 style={{ margin: 0 }}>Documents</h2>
                    <p style={{ color: themeColors.textSecondary, margin: '8px 0 0' }}>
                      문서를 선택하여 AI 질의에 활용하세요. 선택됨: {selectedDocuments.length}개
                    </p>
                  </div>
                  <button
                    onClick={() => setShowUploadModal(true)}
                    style={{ ...tabStyle(true), display: 'flex', alignItems: 'center', gap: '8px' }}
                  >
                    📤 Upload Document
                  </button>
                </div>

                {/* Supported Formats Info */}
                <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap', marginBottom: '16px', padding: '12px', background: 'rgba(74,144,217,0.1)', borderRadius: '8px' }}>
                  <span style={{ color: themeColors.textSecondary, fontSize: '12px' }}>Supported:</span>
                  {Object.entries(SUPPORTED_FORMATS).map(([type, info]) => (
                    <span key={type} style={{ fontSize: '12px', display: 'flex', alignItems: 'center', gap: '4px' }}>
                      <span>{info.icon}</span>
                      <span style={{ color: themeColors.textSecondary }}>{info.extensions.join(', ')}</span>
                    </span>
                  ))}
                </div>

                {/* Documents Grid */}
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))', gap: '12px' }}>
                  {documents.map(doc => {
                    const fileInfo = getFileTypeInfo(doc.original_name);
                    return (
                      <div
                        key={doc.id}
                        onClick={() => {
                          setSelectedDocuments(prev =>
                            prev.includes(doc.id)
                              ? prev.filter(id => id !== doc.id)
                              : [...prev, doc.id]
                          );
                        }}
                        style={{
                          ...cardStyle,
                          cursor: 'pointer',
                          border: selectedDocuments.includes(doc.id)
                            ? `2px solid ${themeColors.accent}`
                            : `1px solid ${themeColors.cardBorder}`,
                          display: 'flex',
                          gap: '12px',
                          alignItems: 'flex-start'
                        }}
                      >
                        <div style={{
                          width: '48px',
                          height: '48px',
                          borderRadius: '8px',
                          background: `${fileInfo.color}20`,
                          display: 'flex',
                          alignItems: 'center',
                          justifyContent: 'center',
                          fontSize: '24px',
                          flexShrink: 0
                        }}>
                          {fileInfo.icon}
                        </div>
                        <div style={{ flex: 1, minWidth: 0 }}>
                          <div style={{ fontWeight: 600, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                            {doc.original_name}
                          </div>
                          <div style={{ fontSize: '12px', color: themeColors.textSecondary, marginTop: '4px' }}>
                            {doc.chunks_count} chunks | {doc.status}
                            {doc.file_size && ` | ${formatFileSize(doc.file_size)}`}
                          </div>
                          <div style={{ display: 'flex', gap: '6px', marginTop: '8px' }}>
                            <span style={{
                              fontSize: '10px',
                              padding: '2px 6px',
                              background: `${fileInfo.color}30`,
                              color: fileInfo.color,
                              borderRadius: '4px'
                            }}>
                              {fileInfo.type.toUpperCase()}
                            </span>
                            {doc.vlm_processed && (
                              <span style={{
                                fontSize: '10px',
                                padding: '2px 6px',
                                background: 'rgba(155, 89, 182, 0.3)',
                                color: '#9B59B6',
                                borderRadius: '4px'
                              }}>
                                VLM
                              </span>
                            )}
                            {doc.processing_mode && doc.processing_mode !== 'text_only' && (
                              <span style={{
                                fontSize: '10px',
                                padding: '2px 6px',
                                background: 'rgba(46, 204, 113, 0.3)',
                                color: '#2ECC71',
                                borderRadius: '4px'
                              }}>
                                {doc.processing_mode}
                              </span>
                            )}
                          </div>
                        </div>
                        {selectedDocuments.includes(doc.id) && (
                          <div style={{ color: themeColors.accent, fontSize: '20px' }}>✓</div>
                        )}
                      </div>
                    );
                  })}
                </div>

                {documents.length === 0 && (
                  <div style={{ textAlign: 'center', padding: '40px', color: themeColors.textSecondary }}>
                    <div style={{ fontSize: '48px', marginBottom: '16px' }}>📁</div>
                    <p>No documents uploaded yet.</p>
                    <button
                      onClick={() => setShowUploadModal(true)}
                      style={{ ...tabStyle(true), marginTop: '16px' }}
                    >
                      Upload your first document
                    </button>
                  </div>
                )}
              </div>

              {/* Upload Modal */}
              <AnimatePresence>
                {showUploadModal && (
                  <motion.div
                    initial={{ opacity: 0 }}
                    animate={{ opacity: 1 }}
                    exit={{ opacity: 0 }}
                    style={{
                      position: 'fixed',
                      top: 0,
                      left: 0,
                      right: 0,
                      bottom: 0,
                      background: 'rgba(0,0,0,0.7)',
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                      zIndex: 1000
                    }}
                    onClick={() => !uploading && setShowUploadModal(false)}
                  >
                    <motion.div
                      initial={{ scale: 0.9, opacity: 0 }}
                      animate={{ scale: 1, opacity: 1 }}
                      exit={{ scale: 0.9, opacity: 0 }}
                      onClick={(e) => e.stopPropagation()}
                      style={{
                        ...cardStyle,
                        width: '500px',
                        maxWidth: '90vw',
                        maxHeight: '90vh',
                        overflow: 'auto'
                      }}
                    >
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '20px' }}>
                        <h2 style={{ margin: 0 }}>Upload Document</h2>
                        <button
                          onClick={() => !uploading && setShowUploadModal(false)}
                          disabled={uploading}
                          style={{ background: 'transparent', border: 'none', color: themeColors.text, fontSize: '24px', cursor: 'pointer' }}
                        >
                          ×
                        </button>
                      </div>

                      {/* File Drop Zone */}
                      <div
                        style={{
                          border: `2px dashed ${uploadFile ? themeColors.accent : themeColors.cardBorder}`,
                          borderRadius: '12px',
                          padding: '40px 20px',
                          textAlign: 'center',
                          marginBottom: '20px',
                          background: uploadFile ? 'rgba(74,144,217,0.1)' : 'transparent',
                          transition: 'all 0.2s'
                        }}
                      >
                        {uploadFile ? (
                          <div>
                            <div style={{ fontSize: '48px', marginBottom: '12px' }}>
                              {getFileTypeInfo(uploadFile.name).icon}
                            </div>
                            <div style={{ fontWeight: 600 }}>{uploadFile.name}</div>
                            <div style={{ fontSize: '12px', color: themeColors.textSecondary, marginTop: '4px' }}>
                              {formatFileSize(uploadFile.size)}
                            </div>
                            <button
                              onClick={() => setUploadFile(null)}
                              style={{ ...tabStyle(false), marginTop: '12px', fontSize: '12px' }}
                            >
                              Remove
                            </button>
                          </div>
                        ) : (
                          <div>
                            <div style={{ fontSize: '48px', marginBottom: '12px' }}>📤</div>
                            <p style={{ margin: 0 }}>Drop file here or click to browse</p>
                            <p style={{ fontSize: '12px', color: themeColors.textSecondary, marginTop: '8px' }}>
                              PDF, Word, Excel, PowerPoint, Text, CSV, JSON, Images
                            </p>
                          </div>
                        )}
                        <input
                          type="file"
                          onChange={handleFileSelect}
                          accept=".pdf,.doc,.docx,.xls,.xlsx,.ppt,.pptx,.txt,.md,.csv,.json,.png,.jpg,.jpeg,.gif,.bmp,.tiff,.webp,.html,.htm"
                          style={{
                            position: 'absolute',
                            top: 0,
                            left: 0,
                            width: '100%',
                            height: '100%',
                            opacity: 0,
                            cursor: 'pointer'
                          }}
                        />
                      </div>

                      {/* Processing Options */}
                      <div style={{ marginBottom: '20px' }}>
                        <h4 style={{ marginBottom: '12px' }}>Processing Options</h4>

                        {/* Processing Mode */}
                        <div style={{ marginBottom: '16px' }}>
                          <label style={{ fontSize: '14px', color: themeColors.textSecondary, display: 'block', marginBottom: '8px' }}>
                            Processing Mode
                          </label>
                          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: '8px' }}>
                            {[
                              { value: 'text_only', label: 'Text Only', desc: 'Basic text extraction' },
                              { value: 'vlm_enhanced', label: 'VLM Enhanced', desc: 'AI-assisted extraction' },
                              { value: 'multimodal', label: 'Multimodal', desc: 'Full image analysis' },
                              { value: 'ocr', label: 'OCR', desc: 'For scanned documents' }
                            ].map(mode => (
                              <div
                                key={mode.value}
                                onClick={() => setUploadSettings(prev => ({ ...prev, processingMode: mode.value as any }))}
                                style={{
                                  padding: '12px',
                                  borderRadius: '8px',
                                  border: uploadSettings.processingMode === mode.value
                                    ? `2px solid ${themeColors.accent}`
                                    : `1px solid ${themeColors.cardBorder}`,
                                  cursor: 'pointer',
                                  background: uploadSettings.processingMode === mode.value ? 'rgba(74,144,217,0.1)' : 'transparent'
                                }}
                              >
                                <div style={{ fontWeight: 600, fontSize: '14px' }}>{mode.label}</div>
                                <div style={{ fontSize: '11px', color: themeColors.textSecondary }}>{mode.desc}</div>
                              </div>
                            ))}
                          </div>
                        </div>

                        {/* Toggle Options */}
                        <div style={{ display: 'flex', gap: '20px', flexWrap: 'wrap' }}>
                          <label style={{ display: 'flex', alignItems: 'center', gap: '8px', cursor: 'pointer' }}>
                            <input
                              type="checkbox"
                              checked={uploadSettings.enableVLM}
                              onChange={(e) => setUploadSettings(prev => ({ ...prev, enableVLM: e.target.checked }))}
                            />
                            <span>Enable VLM Analysis</span>
                          </label>
                          <label style={{ display: 'flex', alignItems: 'center', gap: '8px', cursor: 'pointer' }}>
                            <input
                              type="checkbox"
                              checked={uploadSettings.extractTables}
                              onChange={(e) => setUploadSettings(prev => ({ ...prev, extractTables: e.target.checked }))}
                            />
                            <span>Extract Tables</span>
                          </label>
                          <label style={{ display: 'flex', alignItems: 'center', gap: '8px', cursor: 'pointer' }}>
                            <input
                              type="checkbox"
                              checked={uploadSettings.extractImages}
                              onChange={(e) => setUploadSettings(prev => ({ ...prev, extractImages: e.target.checked }))}
                            />
                            <span>Extract Images</span>
                          </label>
                        </div>
                      </div>

                      {/* Upload Progress */}
                      {uploadProgress && (
                        <div style={{
                          padding: '12px',
                          background: 'rgba(74,144,217,0.2)',
                          borderRadius: '8px',
                          marginBottom: '20px',
                          textAlign: 'center'
                        }}>
                          {uploadProgress}
                        </div>
                      )}

                      {/* Upload Button */}
                      <button
                        onClick={uploadDocument}
                        disabled={!uploadFile || uploading}
                        style={{
                          ...tabStyle(true),
                          width: '100%',
                          padding: '14px',
                          opacity: !uploadFile || uploading ? 0.5 : 1,
                          cursor: !uploadFile || uploading ? 'not-allowed' : 'pointer'
                        }}
                      >
                        {uploading ? 'Processing...' : 'Upload & Process'}
                      </button>
                    </motion.div>
                  </motion.div>
                )}
              </AnimatePresence>
            </motion.div>
          )}

          {/* Web Sources Tab */}
          {activeTab === 'web-sources' && (
            <motion.div
              key="web-sources"
              initial={{ opacity: 0, x: 20 }}
              animate={{ opacity: 1, x: 0 }}
              exit={{ opacity: 0, x: -20 }}
              style={{ flex: 1 }}
            >
              <div style={cardStyle}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' }}>
                  <div>
                    <h2 style={{ margin: 0 }}>🌐 Web Sources</h2>
                    <p style={{ color: themeColors.textSecondary, margin: '8px 0 0' }}>
                      웹 URL을 추가하여 RAG 질의에 활용하세요. NotebookLM 스타일로 웹 콘텐츠를 인덱싱합니다.
                    </p>
                  </div>
                  <button
                    onClick={() => setShowAddUrlModal(true)}
                    style={{ ...tabStyle(true), display: 'flex', alignItems: 'center', gap: '8px' }}
                  >
                    ➕ Add URL
                  </button>
                </div>

                {/* Web Sources Grid */}
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(320px, 1fr))', gap: '12px' }}>
                  {webSources.map(ws => (
                    <div
                      key={ws.id}
                      style={{
                        ...cardStyle,
                        border: `1px solid ${themeColors.cardBorder}`,
                        display: 'flex',
                        flexDirection: 'column',
                        gap: '12px'
                      }}
                    >
                      <div style={{ display: 'flex', gap: '12px', alignItems: 'flex-start' }}>
                        <div style={{
                          width: '48px',
                          height: '48px',
                          borderRadius: '8px',
                          background: ws.status === 'ready' ? 'rgba(46, 204, 113, 0.2)' :
                                     ws.status === 'error' ? 'rgba(231, 76, 60, 0.2)' :
                                     'rgba(74, 144, 217, 0.2)',
                          display: 'flex',
                          alignItems: 'center',
                          justifyContent: 'center',
                          fontSize: '24px',
                          flexShrink: 0
                        }}>
                          {ws.status === 'ready' ? '✅' :
                           ws.status === 'error' ? '❌' :
                           ws.status === 'pending' ? '⏳' : '🔄'}
                        </div>
                        <div style={{ flex: 1, minWidth: 0 }}>
                          <div style={{ fontWeight: 600, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                            {ws.display_name || ws.metadata?.title || ws.domain}
                          </div>
                          <div style={{ fontSize: '12px', color: themeColors.textSecondary, marginTop: '4px', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                            🔗 {ws.url}
                          </div>
                          <div style={{ display: 'flex', gap: '6px', marginTop: '8px', flexWrap: 'wrap' }}>
                            <span style={{
                              fontSize: '10px',
                              padding: '2px 6px',
                              background: ws.status === 'ready' ? 'rgba(46, 204, 113, 0.3)' :
                                         ws.status === 'error' ? 'rgba(231, 76, 60, 0.3)' :
                                         'rgba(241, 196, 15, 0.3)',
                              color: ws.status === 'ready' ? '#2ECC71' :
                                    ws.status === 'error' ? '#E74C3C' : '#F1C40F',
                              borderRadius: '4px'
                            }}>
                              {ws.status.toUpperCase()}
                            </span>
                            {ws.stats?.chunk_count > 0 && (
                              <span style={{
                                fontSize: '10px',
                                padding: '2px 6px',
                                background: 'rgba(155, 89, 182, 0.3)',
                                color: '#9B59B6',
                                borderRadius: '4px'
                              }}>
                                {ws.stats.chunk_count} chunks
                              </span>
                            )}
                            {ws.stats?.word_count > 0 && (
                              <span style={{
                                fontSize: '10px',
                                padding: '2px 6px',
                                background: 'rgba(52, 152, 219, 0.3)',
                                color: '#3498DB',
                                borderRadius: '4px'
                              }}>
                                {ws.stats.word_count.toLocaleString()} words
                              </span>
                            )}
                          </div>
                        </div>
                      </div>
                      {ws.error_message && (
                        <div style={{ fontSize: '12px', color: '#E74C3C', background: 'rgba(231,76,60,0.1)', padding: '8px', borderRadius: '4px' }}>
                          {ws.error_message}
                        </div>
                      )}
                      <div style={{ display: 'flex', gap: '8px', borderTop: `1px solid ${themeColors.cardBorder}`, paddingTop: '12px' }}>
                        <button
                          onClick={() => refreshWebSource(ws.id)}
                          style={{ ...tabStyle(false), flex: 1, fontSize: '12px' }}
                        >
                          🔄 Refresh
                        </button>
                        <button
                          onClick={() => window.open(ws.url, '_blank')}
                          style={{ ...tabStyle(false), flex: 1, fontSize: '12px' }}
                        >
                          🔗 Open
                        </button>
                        <button
                          onClick={() => deleteWebSource(ws.id)}
                          style={{ ...tabStyle(false), flex: 1, fontSize: '12px', color: '#E74C3C' }}
                        >
                          🗑️ Delete
                        </button>
                      </div>
                    </div>
                  ))}
                </div>

                {webSources.length === 0 && (
                  <div style={{ textAlign: 'center', padding: '40px', color: themeColors.textSecondary }}>
                    <div style={{ fontSize: '48px', marginBottom: '16px' }}>🌐</div>
                    <p>No web sources added yet.</p>
                    <p style={{ fontSize: '14px', marginTop: '8px' }}>Add web URLs to index their content for RAG queries.</p>
                    <button
                      onClick={() => setShowAddUrlModal(true)}
                      style={{ ...tabStyle(true), marginTop: '16px' }}
                    >
                      Add your first URL
                    </button>
                  </div>
                )}
              </div>

              {/* Add URL Modal */}
              <AnimatePresence>
                {showAddUrlModal && (
                  <motion.div
                    initial={{ opacity: 0 }}
                    animate={{ opacity: 1 }}
                    exit={{ opacity: 0 }}
                    style={{
                      position: 'fixed',
                      top: 0, left: 0, right: 0, bottom: 0,
                      background: 'rgba(0,0,0,0.7)',
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                      zIndex: 1000
                    }}
                    onClick={() => setShowAddUrlModal(false)}
                  >
                    <motion.div
                      initial={{ scale: 0.9, opacity: 0 }}
                      animate={{ scale: 1, opacity: 1 }}
                      exit={{ scale: 0.9, opacity: 0 }}
                      style={{ ...cardStyle, width: '500px', maxWidth: '90%' }}
                      onClick={e => e.stopPropagation()}
                    >
                      <h3 style={{ margin: '0 0 16px' }}>🌐 Add Web URLs</h3>
                      <p style={{ color: themeColors.textSecondary, fontSize: '14px', marginBottom: '16px' }}>
                        Enter one or more URLs (one per line) to fetch and index their content.
                      </p>

                      <textarea
                        placeholder="https://example.com/article&#10;https://docs.example.com/guide"
                        value={newUrls}
                        onChange={e => setNewUrls(e.target.value)}
                        style={{
                          ...inputStyle,
                          width: '100%',
                          minHeight: '120px',
                          resize: 'vertical',
                          fontFamily: 'monospace'
                        }}
                      />

                      <div style={{ marginTop: '16px' }}>
                        <label style={{ color: themeColors.textSecondary, fontSize: '12px' }}>
                          Tags (optional, comma-separated)
                        </label>
                        <input
                          type="text"
                          placeholder="docs, tutorial, api"
                          value={webSourceTags.join(', ')}
                          onChange={e => setWebSourceTags(e.target.value.split(',').map(t => t.trim()).filter(t => t))}
                          style={{ ...inputStyle, width: '100%', marginTop: '4px' }}
                        />
                      </div>

                      <div style={{ display: 'flex', gap: '12px', marginTop: '20px' }}>
                        <button
                          onClick={() => setShowAddUrlModal(false)}
                          style={{ ...tabStyle(false), flex: 1 }}
                        >
                          Cancel
                        </button>
                        <button
                          onClick={addWebSources}
                          disabled={!newUrls.trim() || addingUrls}
                          style={{
                            ...tabStyle(true),
                            flex: 1,
                            opacity: !newUrls.trim() || addingUrls ? 0.5 : 1,
                            cursor: !newUrls.trim() || addingUrls ? 'not-allowed' : 'pointer'
                          }}
                        >
                          {addingUrls ? 'Adding...' : 'Add URLs'}
                        </button>
                      </div>
                    </motion.div>
                  </motion.div>
                )}
              </AnimatePresence>
            </motion.div>
          )}

          {/* Notes Tab */}
          {activeTab === 'notes' && (
            <motion.div
              key="notes"
              initial={{ opacity: 0, x: 20 }}
              animate={{ opacity: 1, x: 0 }}
              exit={{ opacity: 0, x: -20 }}
              style={{ flex: 1, display: 'flex', gap: '16px' }}
            >
              {/* Folders Sidebar */}
              <div style={{ ...cardStyle, width: '200px', flexShrink: 0 }}>
                <h3 style={{ marginTop: 0 }}>Folders</h3>
                <div
                  onClick={() => setSelectedFolder(null)}
                  style={{
                    padding: '8px',
                    borderRadius: '6px',
                    cursor: 'pointer',
                    background: selectedFolder === null ? 'rgba(74,144,217,0.2)' : 'transparent'
                  }}
                >
                  All Notes
                </div>
                {folders.map(folder => (
                  <div
                    key={folder.id}
                    onClick={() => setSelectedFolder(folder.id)}
                    style={{
                      padding: '8px',
                      borderRadius: '6px',
                      cursor: 'pointer',
                      background: selectedFolder === folder.id ? 'rgba(74,144,217,0.2)' : 'transparent'
                    }}
                  >
                    📁 {folder.name} ({folder.note_count})
                  </div>
                ))}
              </div>

              {/* Notes List */}
              <div style={{ ...cardStyle, flex: 1 }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' }}>
                  <h2 style={{ margin: 0 }}>Notes</h2>
                  <button
                    onClick={() => setSelectedNote(null)}
                    style={{ ...tabStyle(true) }}
                  >
                    + New Note
                  </button>
                </div>

                {/* Search */}
                <div style={{ display: 'flex', gap: '8px', marginBottom: '16px' }}>
                  <input
                    type="text"
                    value={searchQuery}
                    onChange={(e) => setSearchQuery(e.target.value)}
                    placeholder="Search notes..."
                    style={{
                      flex: 1,
                      padding: '10px 14px',
                      background: 'rgba(255,255,255,0.1)',
                      border: `1px solid ${themeColors.cardBorder}`,
                      borderRadius: '8px',
                      color: themeColors.text
                    }}
                  />
                  <button onClick={handleSearch} style={tabStyle(false)}>Search</button>
                </div>

                {/* Notes Grid */}
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(250px, 1fr))', gap: '12px' }}>
                  {notes.map(note => (
                    <div
                      key={note.id}
                      onClick={() => setSelectedNote(note)}
                      style={{
                        ...cardStyle,
                        cursor: 'pointer',
                        position: 'relative'
                      }}
                    >
                      {note.is_pinned && <span style={{ position: 'absolute', top: '8px', right: '8px' }}>📌</span>}
                      <div style={{ fontWeight: 600 }}>{note.title}</div>
                      <div style={{ fontSize: '12px', color: themeColors.textSecondary, marginTop: '8px' }}>
                        {note.preview}
                      </div>
                      <div style={{ display: 'flex', gap: '4px', marginTop: '8px', flexWrap: 'wrap' }}>
                        {note.tags.map((tag, i) => (
                          <span key={i} style={{ fontSize: '10px', padding: '2px 6px', background: 'rgba(74,144,217,0.3)', borderRadius: '4px' }}>
                            {tag}
                          </span>
                        ))}
                      </div>
                    </div>
                  ))}
                </div>
              </div>

              {/* Note Editor */}
              <div style={{ ...cardStyle, width: '400px', flexShrink: 0 }}>
                <h3 style={{ marginTop: 0 }}>{selectedNote ? 'Edit Note' : 'New Note'}</h3>
                <input
                  type="text"
                  value={noteTitle}
                  onChange={(e) => setNoteTitle(e.target.value)}
                  placeholder="Note title..."
                  style={{
                    width: '100%',
                    padding: '10px',
                    marginBottom: '12px',
                    background: 'rgba(255,255,255,0.1)',
                    border: `1px solid ${themeColors.cardBorder}`,
                    borderRadius: '8px',
                    color: themeColors.text
                  }}
                />
                <textarea
                  value={noteContent}
                  onChange={(e) => setNoteContent(e.target.value)}
                  placeholder="Note content (Markdown supported)..."
                  style={{
                    width: '100%',
                    height: '300px',
                    padding: '10px',
                    background: 'rgba(255,255,255,0.1)',
                    border: `1px solid ${themeColors.cardBorder}`,
                    borderRadius: '8px',
                    color: themeColors.text,
                    resize: 'vertical'
                  }}
                />
                <button onClick={createNote} style={{ ...tabStyle(true), width: '100%', marginTop: '12px' }}>
                  Save Note
                </button>
              </div>
            </motion.div>
          )}

          {/* Content Tab */}
          {activeTab === 'content' && (
            <motion.div
              key="content"
              initial={{ opacity: 0, x: 20 }}
              animate={{ opacity: 1, x: 0 }}
              exit={{ opacity: 0, x: -20 }}
              style={{ flex: 1 }}
            >
              <div style={cardStyle}>
                <h2>AI Content Generation</h2>
                <p style={{ color: themeColors.textSecondary }}>
                  선택된 문서 ({selectedDocuments.length}개)를 기반으로 다양한 콘텐츠를 생성합니다.
                </p>

                {/* Content Type Buttons */}
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(150px, 1fr))', gap: '12px', marginTop: '20px' }}>
                  {[
                    { type: 'summary', label: '요약', icon: '📝' },
                    { type: 'faq', label: 'FAQ', icon: '❓' },
                    { type: 'study_guide', label: '학습 가이드', icon: '📚' },
                    { type: 'briefing', label: '브리핑', icon: '📋' },
                    { type: 'timeline', label: '타임라인', icon: '📅' },
                    { type: 'toc', label: '목차', icon: '📑' },
                    { type: 'key_topics', label: '핵심 주제', icon: '🎯' }
                  ].map(ct => (
                    <button
                      key={ct.type}
                      onClick={() => generateContent(ct.type)}
                      disabled={generatingContent || selectedDocuments.length === 0}
                      style={{
                        ...cardStyle,
                        cursor: generatingContent ? 'not-allowed' : 'pointer',
                        textAlign: 'center',
                        opacity: generatingContent || selectedDocuments.length === 0 ? 0.5 : 1
                      }}
                    >
                      <div style={{ fontSize: '32px' }}>{ct.icon}</div>
                      <div style={{ marginTop: '8px', fontWeight: 600 }}>{ct.label}</div>
                    </button>
                  ))}
                </div>

                {generatingContent && (
                  <div style={{ textAlign: 'center', marginTop: '20px', color: themeColors.accent }}>
                    콘텐츠 생성 중...
                  </div>
                )}
              </div>

              {/* Generated Contents List */}
              <div style={{ ...cardStyle, marginTop: '20px' }}>
                <h3>Generated Contents</h3>
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(250px, 1fr))', gap: '12px', marginTop: '16px' }}>
                  {contents.map(content => (
                    <div
                      key={content.id}
                      onClick={() => {
                        setSelectedContent(content);
                        loadContentDetail(content.id);
                      }}
                      style={{
                        ...cardStyle,
                        cursor: 'pointer',
                        border: selectedContent?.id === content.id
                          ? `2px solid ${themeColors.accent}`
                          : `1px solid ${themeColors.cardBorder}`
                      }}
                    >
                      <div style={{ fontWeight: 600 }}>{content.title}</div>
                      <div style={{ fontSize: '12px', color: themeColors.textSecondary }}>
                        {content.content_type} | {content.status}
                      </div>
                    </div>
                  ))}
                </div>
              </div>

              {/* Content Detail */}
              {contentData && (
                <div style={{ ...cardStyle, marginTop: '20px' }}>
                  <h3>{contentData.title}</h3>
                  <pre style={{ whiteSpace: 'pre-wrap', fontSize: '14px' }}>
                    {JSON.stringify(contentData, null, 2)}
                  </pre>
                </div>
              )}
            </motion.div>
          )}

          {/* Projects Tab */}
          {activeTab === 'projects' && (
            <motion.div
              key="projects"
              initial={{ opacity: 0, x: 20 }}
              animate={{ opacity: 1, x: 0 }}
              exit={{ opacity: 0, x: -20 }}
              style={{ flex: 1 }}
            >
              <div style={cardStyle}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <h2 style={{ margin: 0 }}>Projects</h2>
                  <button
                    onClick={() => {
                      const name = prompt('프로젝트 이름:');
                      if (name) createProject(name, '');
                    }}
                    style={tabStyle(true)}
                  >
                    + New Project
                  </button>
                </div>

                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(300px, 1fr))', gap: '16px', marginTop: '20px' }}>
                  {projects.map(project => (
                    <div
                      key={project.id}
                      onClick={() => setSelectedProject(project)}
                      style={{
                        ...cardStyle,
                        cursor: 'pointer',
                        border: selectedProject?.id === project.id
                          ? `2px solid ${themeColors.accent}`
                          : `1px solid ${themeColors.cardBorder}`
                      }}
                    >
                      <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                        <div style={{
                          width: '40px',
                          height: '40px',
                          borderRadius: '8px',
                          background: project.color || themeColors.accent,
                          display: 'flex',
                          alignItems: 'center',
                          justifyContent: 'center',
                          fontSize: '20px'
                        }}>
                          📁
                        </div>
                        <div>
                          <div style={{ fontWeight: 600 }}>{project.name}</div>
                          <div style={{ fontSize: '12px', color: themeColors.textSecondary }}>
                            {project.document_count} docs | {project.note_count} notes
                          </div>
                        </div>
                      </div>
                      {project.description && (
                        <div style={{ marginTop: '12px', fontSize: '14px', color: themeColors.textSecondary }}>
                          {project.description}
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            </motion.div>
          )}

          {/* Knowledge Graph Tab */}
          {activeTab === 'knowledge-graph' && (
            <motion.div
              key="knowledge-graph"
              initial={{ opacity: 0, x: 20 }}
              animate={{ opacity: 1, x: 0 }}
              exit={{ opacity: 0, x: -20 }}
              style={{ flex: 1, display: 'flex', flexDirection: 'column', gap: '16px' }}
            >
              {/* Header */}
              <div style={cardStyle}>
                <h2 style={{ margin: 0 }}>Knowledge Graph</h2>
                <p style={{ color: themeColors.textSecondary, margin: '8px 0 0' }}>
                  쿼리 기반 지식 그래프 생성 및 탐색 - 선택된 문서: {selectedDocuments.length}개
                </p>
              </div>

              {/* Query Input & Actions */}
              <div style={{ ...cardStyle, display: 'flex', gap: '12px', flexWrap: 'wrap' }}>
                <input
                  type="text"
                  value={kgQuery}
                  onChange={(e) => setKgQuery(e.target.value)}
                  placeholder="Knowledge Graph를 생성하거나 질의할 내용을 입력하세요..."
                  style={{
                    flex: 1,
                    minWidth: '300px',
                    padding: '12px 16px',
                    background: 'rgba(255,255,255,0.1)',
                    border: `1px solid ${themeColors.cardBorder}`,
                    borderRadius: '8px',
                    color: themeColors.text,
                    fontSize: '16px'
                  }}
                  onKeyPress={(e) => e.key === 'Enter' && (selectedKG ? queryKnowledgeGraph() : buildKnowledgeGraph())}
                />
                <button
                  onClick={buildKnowledgeGraph}
                  disabled={buildingKG || !kgQuery.trim()}
                  style={{
                    padding: '12px 24px',
                    background: '#2ECC71',
                    color: '#fff',
                    border: 'none',
                    borderRadius: '8px',
                    cursor: buildingKG || !kgQuery.trim() ? 'not-allowed' : 'pointer',
                    opacity: buildingKG || !kgQuery.trim() ? 0.5 : 1,
                    display: 'flex',
                    alignItems: 'center',
                    gap: '8px'
                  }}
                >
                  {buildingKG ? '생성 중...' : '🔗 KG 생성'}
                </button>
                {selectedKG && (
                  <button
                    onClick={queryKnowledgeGraph}
                    disabled={queryingKG || !kgQuery.trim()}
                    style={{
                      padding: '12px 24px',
                      background: themeColors.accent,
                      color: '#fff',
                      border: 'none',
                      borderRadius: '8px',
                      cursor: queryingKG || !kgQuery.trim() ? 'not-allowed' : 'pointer',
                      opacity: queryingKG || !kgQuery.trim() ? 0.5 : 1,
                      display: 'flex',
                      alignItems: 'center',
                      gap: '8px'
                    }}
                  >
                    {queryingKG ? '질의 중...' : '🔍 KG 질의'}
                  </button>
                )}
              </div>

              {/* Main Content Area */}
              <div style={{ display: 'flex', gap: '16px', flex: 1 }}>
                {/* KG List Sidebar */}
                <div style={{ ...cardStyle, width: '250px', flexShrink: 0 }}>
                  <h3 style={{ margin: '0 0 16px' }}>Knowledge Graphs</h3>
                  {knowledgeGraphs.length === 0 ? (
                    <div style={{ color: themeColors.textSecondary, fontSize: '14px', textAlign: 'center', padding: '20px 0' }}>
                      생성된 Knowledge Graph가 없습니다.
                    </div>
                  ) : (
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                      {knowledgeGraphs.map(kg => (
                        <div
                          key={kg.id}
                          onClick={() => setSelectedKG(kg)}
                          style={{
                            padding: '12px',
                            borderRadius: '8px',
                            cursor: 'pointer',
                            background: selectedKG?.id === kg.id ? 'rgba(74,144,217,0.2)' : 'rgba(255,255,255,0.05)',
                            border: selectedKG?.id === kg.id ? `2px solid ${themeColors.accent}` : '1px solid transparent',
                            position: 'relative'
                          }}
                        >
                          <div style={{ fontWeight: 600, fontSize: '14px', marginBottom: '4px' }}>{kg.name}</div>
                          <div style={{ fontSize: '12px', color: themeColors.textSecondary }}>
                            {kg.entity_count} entities | {kg.relationship_count} relationships
                          </div>
                          <button
                            onClick={(e) => {
                              e.stopPropagation();
                              deleteKnowledgeGraph(kg.id);
                            }}
                            style={{
                              position: 'absolute',
                              top: '8px',
                              right: '8px',
                              background: 'transparent',
                              border: 'none',
                              color: '#E74C3C',
                              cursor: 'pointer',
                              fontSize: '14px',
                              padding: '4px'
                            }}
                          >
                            ×
                          </button>
                        </div>
                      ))}
                    </div>
                  )}
                </div>

                {/* Graph Visualization */}
                <div style={{ ...cardStyle, flex: 1, display: 'flex', flexDirection: 'column' }}>
                  {selectedKG ? (
                    <>
                      {/* KG Header */}
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' }}>
                        <div>
                          <h3 style={{ margin: 0 }}>{selectedKG.name}</h3>
                          <div style={{ fontSize: '12px', color: themeColors.textSecondary, marginTop: '4px' }}>
                            {selectedKG.source_query && `Query: "${selectedKG.source_query}"`}
                          </div>
                        </div>
                        <div style={{ display: 'flex', gap: '8px' }}>
                          <span style={{ padding: '4px 8px', background: 'rgba(46,204,113,0.2)', borderRadius: '4px', fontSize: '12px' }}>
                            {selectedKG.entity_count} Entities
                          </span>
                          <span style={{ padding: '4px 8px', background: 'rgba(74,144,217,0.2)', borderRadius: '4px', fontSize: '12px' }}>
                            {selectedKG.relationship_count} Relations
                          </span>
                        </div>
                      </div>

                      {/* KG Answer */}
                      {kgAnswer && (
                        <div style={{
                          padding: '16px',
                          background: 'rgba(74,144,217,0.1)',
                          borderRadius: '8px',
                          marginBottom: '16px',
                          borderLeft: `4px solid ${themeColors.accent}`
                        }}>
                          <div style={{ fontWeight: 600, marginBottom: '8px' }}>AI 답변:</div>
                          <div style={{ whiteSpace: 'pre-wrap' }}>{kgAnswer}</div>
                        </div>
                      )}

                      {/* Graph SVG Visualization */}
                      <div style={{
                        flex: 1,
                        minHeight: '400px',
                        background: 'rgba(0,0,0,0.2)',
                        borderRadius: '8px',
                        position: 'relative',
                        overflow: 'hidden'
                      }}>
                        <svg width="100%" height="100%" style={{ display: 'block' }}>
                          <defs>
                            <marker
                              id="arrowhead"
                              markerWidth="10"
                              markerHeight="7"
                              refX="10"
                              refY="3.5"
                              orient="auto"
                            >
                              <polygon points="0 0, 10 3.5, 0 7" fill={themeColors.textSecondary} />
                            </marker>
                          </defs>

                          {/* Relationships (Edges) */}
                          {selectedKG.relationships.map((rel, idx) => {
                            const sourceEntity = selectedKG.entities.find(e => e.id === rel.source_id);
                            const targetEntity = selectedKG.entities.find(e => e.id === rel.target_id);
                            if (!sourceEntity || !targetEntity) return null;

                            // Calculate positions in a circular layout if not set
                            const entityCount = selectedKG.entities.length;
                            const sourceIndex = selectedKG.entities.findIndex(e => e.id === rel.source_id);
                            const targetIndex = selectedKG.entities.findIndex(e => e.id === rel.target_id);
                            const centerX = 400;
                            const centerY = 250;
                            const radius = Math.min(300, Math.max(150, entityCount * 20));

                            const sourceX = sourceEntity.x ?? (centerX + radius * Math.cos(2 * Math.PI * sourceIndex / entityCount));
                            const sourceY = sourceEntity.y ?? (centerY + radius * Math.sin(2 * Math.PI * sourceIndex / entityCount));
                            const targetX = targetEntity.x ?? (centerX + radius * Math.cos(2 * Math.PI * targetIndex / entityCount));
                            const targetY = targetEntity.y ?? (centerY + radius * Math.sin(2 * Math.PI * targetIndex / entityCount));

                            // Calculate midpoint for label
                            const midX = (sourceX + targetX) / 2;
                            const midY = (sourceY + targetY) / 2;

                            return (
                              <g key={rel.id || idx}>
                                <line
                                  x1={sourceX}
                                  y1={sourceY}
                                  x2={targetX}
                                  y2={targetY}
                                  stroke={themeColors.textSecondary}
                                  strokeWidth={Math.max(1, rel.weight * 2)}
                                  strokeOpacity={0.5}
                                  markerEnd="url(#arrowhead)"
                                />
                                <text
                                  x={midX}
                                  y={midY - 5}
                                  fill={themeColors.textSecondary}
                                  fontSize="10"
                                  textAnchor="middle"
                                  style={{ pointerEvents: 'none' }}
                                >
                                  {rel.relation_type.replace(/_/g, ' ')}
                                </text>
                              </g>
                            );
                          })}

                          {/* Entities (Nodes) */}
                          {selectedKG.entities.map((entity, idx) => {
                            const entityCount = selectedKG.entities.length;
                            const centerX = 400;
                            const centerY = 250;
                            const radius = Math.min(300, Math.max(150, entityCount * 20));
                            const x = entity.x ?? (centerX + radius * Math.cos(2 * Math.PI * idx / entityCount));
                            const y = entity.y ?? (centerY + radius * Math.sin(2 * Math.PI * idx / entityCount));
                            const nodeRadius = 25 + (entity.confidence * 10);
                            const color = entity.color || getEntityColor(entity.entity_type);

                            return (
                              <g key={entity.id} style={{ cursor: 'pointer' }}>
                                {/* Node circle */}
                                <circle
                                  cx={x}
                                  cy={y}
                                  r={nodeRadius}
                                  fill={color}
                                  fillOpacity={0.8}
                                  stroke={color}
                                  strokeWidth={2}
                                />
                                {/* Entity label */}
                                <text
                                  x={x}
                                  y={y + 4}
                                  fill="#fff"
                                  fontSize="11"
                                  textAnchor="middle"
                                  style={{ pointerEvents: 'none', fontWeight: 600 }}
                                >
                                  {entity.label.length > 10 ? entity.label.substring(0, 10) + '...' : entity.label}
                                </text>
                                {/* Entity type badge */}
                                <text
                                  x={x}
                                  y={y + nodeRadius + 14}
                                  fill={themeColors.textSecondary}
                                  fontSize="9"
                                  textAnchor="middle"
                                  style={{ pointerEvents: 'none' }}
                                >
                                  {entity.entity_type}
                                </text>
                              </g>
                            );
                          })}
                        </svg>

                        {/* Legend */}
                        <div style={{
                          position: 'absolute',
                          bottom: '12px',
                          left: '12px',
                          background: 'rgba(0,0,0,0.7)',
                          padding: '8px 12px',
                          borderRadius: '8px',
                          display: 'flex',
                          flexWrap: 'wrap',
                          gap: '8px',
                          maxWidth: '400px'
                        }}>
                          {Array.from(new Set(selectedKG.entities.map(e => e.entity_type))).map(type => (
                            <div key={type} style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
                              <div style={{
                                width: '12px',
                                height: '12px',
                                borderRadius: '50%',
                                background: getEntityColor(type)
                              }} />
                              <span style={{ fontSize: '10px', color: themeColors.text }}>{type}</span>
                            </div>
                          ))}
                        </div>
                      </div>

                      {/* Entity/Relationship Details */}
                      <div style={{ display: 'flex', gap: '16px', marginTop: '16px' }}>
                        {/* Entities List */}
                        <div style={{ flex: 1 }}>
                          <h4 style={{ margin: '0 0 8px' }}>Entities ({selectedKG.entity_count})</h4>
                          <div style={{ maxHeight: '200px', overflow: 'auto' }}>
                            {selectedKG.entities.slice(0, 20).map(entity => (
                              <div
                                key={entity.id}
                                style={{
                                  padding: '8px',
                                  background: 'rgba(255,255,255,0.05)',
                                  borderRadius: '6px',
                                  marginBottom: '4px',
                                  display: 'flex',
                                  alignItems: 'center',
                                  gap: '8px'
                                }}
                              >
                                <div style={{
                                  width: '10px',
                                  height: '10px',
                                  borderRadius: '50%',
                                  background: getEntityColor(entity.entity_type)
                                }} />
                                <span style={{ fontWeight: 500 }}>{entity.label}</span>
                                <span style={{ fontSize: '11px', color: themeColors.textSecondary }}>
                                  ({entity.entity_type})
                                </span>
                              </div>
                            ))}
                            {selectedKG.entities.length > 20 && (
                              <div style={{ fontSize: '12px', color: themeColors.textSecondary, padding: '8px' }}>
                                + {selectedKG.entities.length - 20} more entities
                              </div>
                            )}
                          </div>
                        </div>

                        {/* Relationships List */}
                        <div style={{ flex: 1 }}>
                          <h4 style={{ margin: '0 0 8px' }}>Relationships ({selectedKG.relationship_count})</h4>
                          <div style={{ maxHeight: '200px', overflow: 'auto' }}>
                            {selectedKG.relationships.slice(0, 20).map(rel => {
                              const source = selectedKG.entities.find(e => e.id === rel.source_id);
                              const target = selectedKG.entities.find(e => e.id === rel.target_id);
                              return (
                                <div
                                  key={rel.id}
                                  style={{
                                    padding: '8px',
                                    background: 'rgba(255,255,255,0.05)',
                                    borderRadius: '6px',
                                    marginBottom: '4px',
                                    fontSize: '12px'
                                  }}
                                >
                                  <span style={{ fontWeight: 500 }}>{source?.label || '?'}</span>
                                  <span style={{ color: themeColors.accent, margin: '0 6px' }}>
                                    → {rel.relation_type.replace(/_/g, ' ')} →
                                  </span>
                                  <span style={{ fontWeight: 500 }}>{target?.label || '?'}</span>
                                </div>
                              );
                            })}
                            {selectedKG.relationships.length > 20 && (
                              <div style={{ fontSize: '12px', color: themeColors.textSecondary, padding: '8px' }}>
                                + {selectedKG.relationships.length - 20} more relationships
                              </div>
                            )}
                          </div>
                        </div>
                      </div>
                    </>
                  ) : (
                    <div style={{ flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', color: themeColors.textSecondary }}>
                      <div style={{ fontSize: '64px', marginBottom: '16px' }}>🔗</div>
                      <h3>Knowledge Graph를 생성하세요</h3>
                      <p style={{ textAlign: 'center', maxWidth: '400px', marginTop: '8px' }}>
                        쿼리를 입력하고 'KG 생성' 버튼을 클릭하면 관련 개념, 관계를 추출하여 지식 그래프를 구축합니다.
                      </p>
                      <div style={{ display: 'flex', gap: '8px', marginTop: '20px', flexWrap: 'wrap', justifyContent: 'center' }}>
                        {[
                          'GPU 기반 RAG 시스템 구조',
                          'Neo4j Knowledge Graph',
                          'LLM과 벡터 검색의 관계'
                        ].map((example, i) => (
                          <button
                            key={i}
                            onClick={() => setKgQuery(example)}
                            style={{
                              ...tabStyle(false),
                              fontSize: '12px',
                              padding: '8px 12px'
                            }}
                          >
                            {example}
                          </button>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              </div>
            </motion.div>
          )}

          {/* Knowledge Articles Tab */}
          {activeTab === 'knowledge-articles' && (
            <motion.div
              key="knowledge-articles"
              initial={{ opacity: 0, x: 20 }}
              animate={{ opacity: 1, x: 0 }}
              exit={{ opacity: 0, x: -20 }}
              style={{ flex: 1, display: 'flex', flexDirection: 'column', gap: '16px' }}
            >
              {/* Header */}
              <div style={cardStyle}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <div>
                    <h2 style={{ margin: 0 }}>Knowledge Base</h2>
                    <p style={{ color: themeColors.textSecondary, margin: '8px 0 0' }}>
                      지식 등록, 검수, 공유 시스템
                    </p>
                  </div>
                  <div style={{ display: 'flex', gap: '8px' }}>
                    {/* Language Selector */}
                    <div style={{ display: 'flex', gap: '4px' }}>
                      {(['ko', 'ja', 'en'] as SupportedLanguage[]).map(lang => (
                        <button
                          key={lang}
                          onClick={() => setArticleLanguage(lang)}
                          style={{
                            padding: '8px 12px',
                            border: 'none',
                            borderRadius: '6px',
                            background: articleLanguage === lang ? themeColors.accent : 'rgba(255,255,255,0.1)',
                            color: articleLanguage === lang ? '#fff' : themeColors.text,
                            cursor: 'pointer',
                            fontSize: '12px',
                            fontWeight: 600
                          }}
                        >
                          {lang.toUpperCase()}
                        </button>
                      ))}
                    </div>
                    <button
                      onClick={() => setShowCreateArticle(true)}
                      style={{ ...tabStyle(true), display: 'flex', alignItems: 'center', gap: '8px' }}
                    >
                      + New Knowledge
                    </button>
                  </div>
                </div>
              </div>

              {/* Main Content */}
              <div style={{ display: 'flex', gap: '16px', flex: 1 }}>
                {/* Articles List */}
                <div style={{ ...cardStyle, flex: 1 }}>
                  <h3 style={{ margin: '0 0 16px' }}>Published Knowledge</h3>

                  {knowledgeArticles.length === 0 ? (
                    <div style={{ textAlign: 'center', padding: '40px', color: themeColors.textSecondary }}>
                      <div style={{ fontSize: '48px', marginBottom: '16px' }}>📚</div>
                      <p>등록된 지식이 없습니다.</p>
                    </div>
                  ) : (
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
                      {knowledgeArticles.map(article => (
                        <div
                          key={article.id}
                          onClick={() => setSelectedArticle(article)}
                          style={{
                            padding: '16px',
                            background: selectedArticle?.id === article.id ? 'rgba(74,144,217,0.2)' : 'rgba(255,255,255,0.05)',
                            borderRadius: '8px',
                            cursor: 'pointer',
                            border: selectedArticle?.id === article.id ? `2px solid ${themeColors.accent}` : '1px solid transparent'
                          }}
                        >
                          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
                            <div style={{ flex: 1 }}>
                              <div style={{ fontWeight: 600, fontSize: '16px' }}>{article.title}</div>
                              <div style={{ fontSize: '12px', color: themeColors.textSecondary, marginTop: '4px' }}>
                                {article.author_name} | {article.category} | {new Date(article.created_at).toLocaleDateString()}
                              </div>
                              {article.summary && (
                                <div style={{ fontSize: '13px', color: themeColors.textSecondary, marginTop: '8px' }}>
                                  {article.summary}
                                </div>
                              )}
                            </div>
                            <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-end', gap: '4px' }}>
                              <span style={{
                                padding: '4px 8px',
                                background: `${getStatusColor(article.status)}30`,
                                color: getStatusColor(article.status),
                                borderRadius: '4px',
                                fontSize: '11px'
                              }}>
                                {getStatusLabel(article.status)}
                              </span>
                              <div style={{ display: 'flex', gap: '12px', fontSize: '12px', color: themeColors.textSecondary }}>
                                <span>👁️ {article.view_count}</span>
                                <span>👍 {article.recommendation_count}</span>
                              </div>
                            </div>
                          </div>
                          <div style={{ display: 'flex', gap: '6px', marginTop: '8px', flexWrap: 'wrap' }}>
                            {article.tags.map((tag, i) => (
                              <span key={i} style={{
                                fontSize: '10px',
                                padding: '2px 6px',
                                background: 'rgba(74,144,217,0.2)',
                                borderRadius: '4px'
                              }}>
                                {tag}
                              </span>
                            ))}
                          </div>
                        </div>
                      ))}
                    </div>
                  )}
                </div>

                {/* Right Sidebar */}
                <div style={{ width: '300px', display: 'flex', flexDirection: 'column', gap: '16px' }}>
                  {/* Pending Reviews (for reviewers only) */}
                  {(user?.role === 'senior' || user?.role === 'leader' || user?.role === 'admin') && pendingReviews.length > 0 && (
                    <div style={cardStyle}>
                      <h3 style={{ margin: '0 0 12px', color: '#F39C12' }}>Pending Reviews ({pendingReviews.length})</h3>
                      {pendingReviews.map(article => (
                        <div
                          key={article.id}
                          onClick={() => setSelectedArticle(article)}
                          style={{
                            padding: '10px',
                            background: 'rgba(243,156,18,0.1)',
                            borderRadius: '6px',
                            marginBottom: '8px',
                            cursor: 'pointer'
                          }}
                        >
                          <div style={{ fontWeight: 500, fontSize: '13px' }}>{article.title}</div>
                          <div style={{ fontSize: '11px', color: themeColors.textSecondary }}>
                            by {article.author_name}
                          </div>
                        </div>
                      ))}
                    </div>
                  )}

                  {/* Top Contributors */}
                  <div style={cardStyle}>
                    <h3 style={{ margin: '0 0 12px' }}>Top Contributors</h3>
                    {topContributors.length === 0 ? (
                      <div style={{ color: themeColors.textSecondary, fontSize: '13px' }}>
                        No contributors yet
                      </div>
                    ) : (
                      topContributors.map((contributor, idx) => (
                        <div
                          key={contributor.user_id}
                          style={{
                            display: 'flex',
                            alignItems: 'center',
                            gap: '10px',
                            padding: '8px 0',
                            borderBottom: idx < topContributors.length - 1 ? `1px solid ${themeColors.cardBorder}` : 'none'
                          }}
                        >
                          <div style={{
                            width: '24px',
                            height: '24px',
                            borderRadius: '50%',
                            background: idx < 3 ? ['#FFD700', '#C0C0C0', '#CD7F32'][idx] : themeColors.cardBg,
                            display: 'flex',
                            alignItems: 'center',
                            justifyContent: 'center',
                            fontSize: '12px',
                            fontWeight: 600
                          }}>
                            {contributor.rank}
                          </div>
                          <div style={{ flex: 1 }}>
                            <div style={{ fontWeight: 500, fontSize: '13px' }}>{contributor.username}</div>
                            <div style={{ fontSize: '11px', color: themeColors.textSecondary }}>
                              {contributor.article_count} articles | {contributor.total_recommendations} recommendations
                            </div>
                          </div>
                        </div>
                      ))
                    )}
                  </div>

                  {/* Categories */}
                  <div style={cardStyle}>
                    <h3 style={{ margin: '0 0 12px' }}>Categories</h3>
                    {categories.map(cat => (
                      <div
                        key={cat.value}
                        style={{
                          padding: '8px',
                          borderRadius: '6px',
                          marginBottom: '4px',
                          cursor: 'pointer',
                          background: 'rgba(255,255,255,0.05)'
                        }}
                      >
                        {cat.label}
                      </div>
                    ))}
                  </div>
                </div>
              </div>

              {/* Article Detail Modal */}
              <AnimatePresence>
                {selectedArticle && (
                  <motion.div
                    initial={{ opacity: 0 }}
                    animate={{ opacity: 1 }}
                    exit={{ opacity: 0 }}
                    style={{
                      position: 'fixed',
                      top: 0,
                      left: 0,
                      right: 0,
                      bottom: 0,
                      background: 'rgba(0,0,0,0.7)',
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                      zIndex: 1000
                    }}
                    onClick={() => setSelectedArticle(null)}
                  >
                    <motion.div
                      initial={{ scale: 0.9, opacity: 0 }}
                      animate={{ scale: 1, opacity: 1 }}
                      exit={{ scale: 0.9, opacity: 0 }}
                      onClick={(e) => e.stopPropagation()}
                      style={{
                        ...cardStyle,
                        width: '800px',
                        maxWidth: '90vw',
                        maxHeight: '90vh',
                        overflow: 'auto'
                      }}
                    >
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '20px' }}>
                        <div>
                          <span style={{
                            padding: '4px 8px',
                            background: `${getStatusColor(selectedArticle.status)}30`,
                            color: getStatusColor(selectedArticle.status),
                            borderRadius: '4px',
                            fontSize: '11px',
                            marginBottom: '8px',
                            display: 'inline-block'
                          }}>
                            {getStatusLabel(selectedArticle.status)}
                          </span>
                          <h2 style={{ margin: '8px 0 0' }}>{selectedArticle.title}</h2>
                          <div style={{ fontSize: '13px', color: themeColors.textSecondary, marginTop: '8px' }}>
                            {selectedArticle.author_name} {selectedArticle.author_department && `(${selectedArticle.author_department})`} | {new Date(selectedArticle.created_at).toLocaleString()}
                          </div>
                        </div>
                        <button
                          onClick={() => setSelectedArticle(null)}
                          style={{ background: 'transparent', border: 'none', color: themeColors.text, fontSize: '24px', cursor: 'pointer' }}
                        >
                          ×
                        </button>
                      </div>

                      {/* Language Selector for Article */}
                      <div style={{ display: 'flex', gap: '8px', marginBottom: '16px' }}>
                        {(['ko', 'ja', 'en'] as SupportedLanguage[]).map(lang => (
                          <button
                            key={lang}
                            onClick={() => setArticleLanguage(lang)}
                            style={{
                              padding: '6px 12px',
                              border: 'none',
                              borderRadius: '4px',
                              background: articleLanguage === lang ? themeColors.accent : 'rgba(255,255,255,0.1)',
                              color: articleLanguage === lang ? '#fff' : themeColors.text,
                              cursor: 'pointer',
                              fontSize: '12px'
                            }}
                          >
                            {lang === 'ko' ? '한국어' : lang === 'ja' ? '日本語' : 'English'}
                          </button>
                        ))}
                      </div>

                      {/* Article Content */}
                      <div style={{
                        padding: '20px',
                        background: 'rgba(0,0,0,0.2)',
                        borderRadius: '8px',
                        marginBottom: '16px'
                      }}>
                        {selectedArticle.translations[articleLanguage] ? (
                          <div dangerouslySetInnerHTML={{ __html: selectedArticle.translations[articleLanguage].content }} />
                        ) : (
                          <div dangerouslySetInnerHTML={{ __html: selectedArticle.content }} />
                        )}
                      </div>

                      {/* Actions */}
                      <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
                        <button
                          onClick={() => recommendArticle(selectedArticle.id)}
                          style={{
                            padding: '10px 20px',
                            background: 'rgba(46,204,113,0.2)',
                            border: 'none',
                            borderRadius: '6px',
                            color: '#2ECC71',
                            cursor: 'pointer',
                            display: 'flex',
                            alignItems: 'center',
                            gap: '6px'
                          }}
                        >
                          👍 Recommend ({selectedArticle.recommendation_count})
                        </button>

                        <div style={{ marginLeft: 'auto', fontSize: '13px', color: themeColors.textSecondary }}>
                          Views: {selectedArticle.view_count}
                        </div>

                        {/* Review Actions (for reviewers) */}
                        {selectedArticle.status === 'in_review' && selectedArticle.reviewer_id === user?.id && (
                          <div style={{ display: 'flex', gap: '8px', marginLeft: '16px' }}>
                            <input
                              type="text"
                              value={reviewComment}
                              onChange={(e) => setReviewComment(e.target.value)}
                              placeholder="Review comment..."
                              style={{
                                padding: '8px 12px',
                                background: 'rgba(255,255,255,0.1)',
                                border: `1px solid ${themeColors.cardBorder}`,
                                borderRadius: '6px',
                                color: themeColors.text,
                                width: '200px'
                              }}
                            />
                            <button
                              onClick={() => reviewArticle(selectedArticle.id, 'approve')}
                              style={{ padding: '8px 16px', background: '#2ECC71', border: 'none', borderRadius: '6px', color: '#fff', cursor: 'pointer' }}
                            >
                              Approve
                            </button>
                            <button
                              onClick={() => reviewArticle(selectedArticle.id, 'reject')}
                              style={{ padding: '8px 16px', background: '#E74C3C', border: 'none', borderRadius: '6px', color: '#fff', cursor: 'pointer' }}
                            >
                              Reject
                            </button>
                          </div>
                        )}
                      </div>
                    </motion.div>
                  </motion.div>
                )}
              </AnimatePresence>

              {/* Create Article Modal */}
              <AnimatePresence>
                {showCreateArticle && (
                  <motion.div
                    initial={{ opacity: 0 }}
                    animate={{ opacity: 1 }}
                    exit={{ opacity: 0 }}
                    style={{
                      position: 'fixed',
                      top: 0,
                      left: 0,
                      right: 0,
                      bottom: 0,
                      background: 'rgba(0,0,0,0.7)',
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                      zIndex: 1000
                    }}
                    onClick={() => !savingArticle && setShowCreateArticle(false)}
                  >
                    <motion.div
                      initial={{ scale: 0.9, opacity: 0 }}
                      animate={{ scale: 1, opacity: 1 }}
                      exit={{ scale: 0.9, opacity: 0 }}
                      onClick={(e) => e.stopPropagation()}
                      style={{
                        ...cardStyle,
                        width: '700px',
                        maxWidth: '90vw',
                        maxHeight: '90vh',
                        overflow: 'auto'
                      }}
                    >
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '20px' }}>
                        <h2 style={{ margin: 0 }}>Create New Knowledge</h2>
                        <button
                          onClick={() => !savingArticle && setShowCreateArticle(false)}
                          disabled={savingArticle}
                          style={{ background: 'transparent', border: 'none', color: themeColors.text, fontSize: '24px', cursor: 'pointer' }}
                        >
                          ×
                        </button>
                      </div>

                      <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
                        <div>
                          <label style={{ display: 'block', marginBottom: '6px', fontSize: '14px' }}>Title *</label>
                          <input
                            type="text"
                            value={newArticle.title}
                            onChange={(e) => setNewArticle(prev => ({ ...prev, title: e.target.value }))}
                            placeholder="Enter knowledge title..."
                            style={{
                              width: '100%',
                              padding: '12px',
                              background: 'rgba(255,255,255,0.1)',
                              border: `1px solid ${themeColors.cardBorder}`,
                              borderRadius: '8px',
                              color: themeColors.text,
                              fontSize: '16px'
                            }}
                          />
                        </div>

                        <div>
                          <label style={{ display: 'block', marginBottom: '6px', fontSize: '14px' }}>Category *</label>
                          <select
                            value={newArticle.category}
                            onChange={(e) => setNewArticle(prev => ({ ...prev, category: e.target.value as KnowledgeCategory }))}
                            style={{
                              width: '100%',
                              padding: '12px',
                              background: 'rgba(255,255,255,0.1)',
                              border: `1px solid ${themeColors.cardBorder}`,
                              borderRadius: '8px',
                              color: themeColors.text,
                              fontSize: '14px'
                            }}
                          >
                            {categories.map(cat => (
                              <option key={cat.value} value={cat.value}>{cat.label}</option>
                            ))}
                          </select>
                        </div>

                        <div>
                          <label style={{ display: 'block', marginBottom: '6px', fontSize: '14px' }}>Summary</label>
                          <input
                            type="text"
                            value={newArticle.summary}
                            onChange={(e) => setNewArticle(prev => ({ ...prev, summary: e.target.value }))}
                            placeholder="Brief summary of the knowledge..."
                            style={{
                              width: '100%',
                              padding: '12px',
                              background: 'rgba(255,255,255,0.1)',
                              border: `1px solid ${themeColors.cardBorder}`,
                              borderRadius: '8px',
                              color: themeColors.text,
                              fontSize: '14px'
                            }}
                          />
                        </div>

                        <div>
                          <label style={{ display: 'block', marginBottom: '6px', fontSize: '14px' }}>Content * (HTML/Markdown)</label>
                          <textarea
                            value={newArticle.content}
                            onChange={(e) => setNewArticle(prev => ({ ...prev, content: e.target.value }))}
                            placeholder="Write your knowledge content here..."
                            style={{
                              width: '100%',
                              height: '300px',
                              padding: '12px',
                              background: 'rgba(255,255,255,0.1)',
                              border: `1px solid ${themeColors.cardBorder}`,
                              borderRadius: '8px',
                              color: themeColors.text,
                              fontSize: '14px',
                              resize: 'vertical'
                            }}
                          />
                        </div>

                        <div style={{ display: 'flex', gap: '12px' }}>
                          <button
                            onClick={createKnowledgeArticle}
                            disabled={savingArticle || !newArticle.title.trim() || !newArticle.content.trim()}
                            style={{
                              padding: '12px 24px',
                              background: themeColors.accent,
                              border: 'none',
                              borderRadius: '8px',
                              color: '#fff',
                              cursor: savingArticle ? 'not-allowed' : 'pointer',
                              opacity: savingArticle || !newArticle.title.trim() || !newArticle.content.trim() ? 0.5 : 1
                            }}
                          >
                            {savingArticle ? 'Saving...' : 'Create Draft'}
                          </button>
                          <button
                            onClick={() => setShowCreateArticle(false)}
                            disabled={savingArticle}
                            style={{
                              padding: '12px 24px',
                              background: 'rgba(255,255,255,0.1)',
                              border: 'none',
                              borderRadius: '8px',
                              color: themeColors.text,
                              cursor: 'pointer'
                            }}
                          >
                            Cancel
                          </button>
                        </div>
                      </div>
                    </motion.div>
                  </motion.div>
                )}
              </AnimatePresence>
            </motion.div>
          )}
        </AnimatePresence>

        {/* Source Panel */}
        <AnimatePresence>
          {showSourcePanel && selectedSource && (
            <motion.div
              initial={{ x: 300, opacity: 0 }}
              animate={{ x: 0, opacity: 1 }}
              exit={{ x: 300, opacity: 0 }}
              style={{
                ...cardStyle,
                width: '400px',
                flexShrink: 0,
                position: 'relative'
              }}
            >
              <button
                onClick={() => setShowSourcePanel(false)}
                style={{
                  position: 'absolute',
                  top: '12px',
                  right: '12px',
                  background: 'transparent',
                  border: 'none',
                  color: themeColors.text,
                  cursor: 'pointer',
                  fontSize: '20px'
                }}
              >
                ×
              </button>
              <h3>Source Detail</h3>
              <div style={{ marginTop: '16px' }}>
                <div style={{ fontWeight: 600, marginBottom: '8px' }}>{selectedSource.doc_name}</div>
                <div style={{ fontSize: '12px', color: themeColors.textSecondary, marginBottom: '16px' }}>
                  Chunk #{selectedSource.chunk_index} | 신뢰도: {(selectedSource.score * 100).toFixed(0)}%
                </div>
                <div style={{
                  padding: '12px',
                  background: 'rgba(255,255,255,0.05)',
                  borderRadius: '8px',
                  fontSize: '14px',
                  lineHeight: 1.6,
                  maxHeight: '400px',
                  overflow: 'auto'
                }}>
                  {selectedSource.content}
                </div>
              </div>
            </motion.div>
          )}
        </AnimatePresence>
      </main>
    </div>
  );
};

export default KnowledgeApp;
