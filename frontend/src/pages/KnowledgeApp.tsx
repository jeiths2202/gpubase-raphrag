import React, { useState, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { useNavigate } from 'react-router-dom';
import { useAuthStore } from '../store/authStore';
import { useTranslation } from '../hooks/useTranslation';
// i18n types imported through useTranslation hook

// Import from extracted feature modules
import {
  Project,
  Note,
  Folder,
  Document,
  ContentItem,
  ChatMessage,
  Conversation,
  KnowledgeGraphData,
  KnowledgeStatus,
  KnowledgeCategory,
  SupportedLanguage,
  KnowledgeArticle,
  TopContributor,
  CategoryOption,
  Notification,
  TabType,
  WebSource,
  ThemeType,
} from '../features/knowledge/types';
import { API_BASE } from '../features/knowledge/constants';
import { getThemeColors, getCardStyle, getTabStyle, getInputStyle } from '../features/knowledge/utils';
import { SettingsPopup, ChatTab, DocumentsTab, WebSourcesTab, NotesTab, ContentTab, ProjectsTab, KnowledgeGraphTab, KnowledgeArticlesTab, KnowledgeSidebar } from '../features/knowledge/components';

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

  // Clipboard paste state
  const [clipboardContent, setClipboardContent] = useState<{
    type: 'image' | 'text' | null;
    data: string | null;  // base64 for image, text content for text
    mimeType: string | null;
    preview: string | null;
  }>({ type: null, data: null, mimeType: null, preview: null });

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
    { type: 'notion', name: 'Notion', icon: '📝', descriptionKey: 'notion', authType: 'oauth2' },
    { type: 'github', name: 'GitHub', icon: '🐙', descriptionKey: 'github', authType: 'oauth2' },
    { type: 'google_drive', name: 'Google Drive', icon: '📁', descriptionKey: 'googleDrive', authType: 'oauth2' },
    { type: 'onenote', name: 'OneNote', icon: '📔', descriptionKey: 'onenote', authType: 'oauth2' },
    { type: 'confluence', name: 'Confluence', icon: '📚', descriptionKey: 'confluence', authType: 'api_token' }
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
        content: data.data?.answer || t('knowledge.chat.noResponse' as keyof import('../i18n/types').TranslationKeys),
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
        content: t('knowledge.chat.errorOccurred' as keyof import('../i18n/types').TranslationKeys),
        timestamp: new Date()
      }]);
    } finally {
      setIsLoading(false);
    }
  };

  const generateSuggestedQuestions = (query: string, answer: string) => {
    const suggestions = [
      t('knowledge.chat.followUp.tellMore' as keyof import('../i18n/types').TranslationKeys, { query }),
      t('knowledge.chat.followUp.showExamples' as keyof import('../i18n/types').TranslationKeys),
      t('knowledge.chat.followUp.prosAndCons' as keyof import('../i18n/types').TranslationKeys)
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
      formData.append('title', pasteTitle || t('knowledge.clipboard.pastedText' as keyof import('../i18n/types').TranslationKeys));

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

  // Clipboard paste handler with content type detection
  const handleClipboardPaste = async (e: React.ClipboardEvent) => {
    const clipboardData = e.clipboardData;
    if (!clipboardData) return;

    // Check for image content first
    const items = clipboardData.items;
    for (let i = 0; i < items.length; i++) {
      const item = items[i];

      // Image detection
      if (item.type.startsWith('image/')) {
        e.preventDefault();
        const file = item.getAsFile();
        if (file) {
          const reader = new FileReader();
          reader.onload = (event) => {
            const base64 = event.target?.result as string;
            setClipboardContent({
              type: 'image',
              data: base64,
              mimeType: item.type,
              preview: base64
            });
          };
          reader.readAsDataURL(file);
        }
        return;
      }
    }

    // Text detection (text/plain or text/html)
    const htmlContent = clipboardData.getData('text/html');
    const plainContent = clipboardData.getData('text/plain');

    if (htmlContent || plainContent) {
      // Only show preview for substantial text (> 100 chars)
      const textContent = plainContent || htmlContent;
      if (textContent.length > 100) {
        e.preventDefault();
        setClipboardContent({
          type: 'text',
          data: textContent,
          mimeType: htmlContent ? 'text/html' : 'text/plain',
          preview: textContent.slice(0, 300) + (textContent.length > 300 ? '...' : '')
        });
      }
      // For short text, let it pass through to input normally
    }
  };

  // Clear clipboard content
  const clearClipboardContent = () => {
    setClipboardContent({ type: null, data: null, mimeType: null, preview: null });
  };

  // Add clipboard content to session
  const addClipboardToSession = async () => {
    if (!clipboardContent.data) return;

    setUploadingSessionDoc(true);
    try {
      if (clipboardContent.type === 'image') {
        // Convert base64 to blob and upload
        const response = await fetch(clipboardContent.data);
        const blob = await response.blob();
        const file = new File([blob], `pasted_image_${Date.now()}.png`, { type: clipboardContent.mimeType || 'image/png' });
        await uploadSessionFile(file);
      } else if (clipboardContent.type === 'text') {
        // Upload as text
        const formData = new FormData();
        formData.append('session_id', sessionId);
        formData.append('content', clipboardContent.data);
        formData.append('title', `${t('knowledge.clipboard.pastedText' as keyof import('../i18n/types').TranslationKeys)} ${new Date().toLocaleTimeString()}`);

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
        }
      }
      clearClipboardContent();
    } catch (error) {
      console.error('Failed to add clipboard content:', error);
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
      alert(t('knowledge.content.selectDocumentsFirst' as keyof import('../i18n/types').TranslationKeys));
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
          alert(t('knowledge.content.generationFailed' as keyof import('../i18n/types').TranslationKeys));
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
        alert(t('knowledge.chat.noteSaved' as keyof import('../i18n/types').TranslationKeys));
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
    if (!confirm(t('knowledge.knowledgeGraph.deleteConfirm' as keyof import('../i18n/types').TranslationKeys))) return;

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
        alert(data.message || t('knowledge.knowledgeBase.review.requested' as keyof import('../i18n/types').TranslationKeys));
        loadKnowledgeArticles();
      }
    } catch (error) {
      console.error('Failed to submit for review:', error);
    }
  };

  const reviewArticle = async (articleId: string, action: 'approve' | 'reject' | 'request_changes') => {
    if (!reviewComment.trim()) {
      alert(t('knowledge.knowledgeBase.review.enterComment' as keyof import('../i18n/types').TranslationKeys));
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
        alert(data.message || t('knowledge.knowledgeBase.review.completed' as keyof import('../i18n/types').TranslationKeys));
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
    const statusKeyMap: Record<KnowledgeStatus, string> = {
      draft: 'draft',
      pending: 'pending',
      in_review: 'inReview',
      approved: 'approved',
      rejected: 'rejected',
      published: 'published'
    };
    const key = statusKeyMap[status];
    return key ? t(`knowledge.knowledgeBase.status.${key}` as keyof import('../i18n/types').TranslationKeys) : status;
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

  // Styles - using extracted utility functions
  const themeColors = getThemeColors(theme);
  const cardStyle = getCardStyle(themeColors);
  const tabStyle = (isActive: boolean) => getTabStyle(isActive, themeColors);
  const inputStyle = getInputStyle(themeColors);

  return (
    <div style={{
      minHeight: '100vh',
      background: themeColors.bg,
      color: themeColors.text,
      display: 'flex'
    }}>
      {/* Sidebar */}
      <KnowledgeSidebar
        sidebarCollapsed={sidebarCollapsed}
        showNotifications={showNotifications}
        notifications={notifications}
        unreadCount={unreadCount}
        activeTab={activeTab}
        projects={projects}
        selectedProject={selectedProject}
        theme={theme}
        user={user}
        setSidebarCollapsed={setSidebarCollapsed}
        setShowNotifications={setShowNotifications}
        setActiveTab={setActiveTab}
        setSelectedProject={setSelectedProject}
        setShowSettingsPopup={setShowSettingsPopup}
        markAllNotificationsAsRead={markAllNotificationsAsRead}
        markNotificationAsRead={markNotificationAsRead}
        toggleTheme={toggleTheme}
        logout={logout}
        navigate={navigate}
        themeColors={themeColors}
        cardStyle={cardStyle}
        tabStyle={tabStyle}
        t={t}
      />

      {/* Settings Popup - using extracted component */}
      <SettingsPopup
        isOpen={showSettingsPopup}
        onClose={() => setShowSettingsPopup(false)}
        language={language}
        setLanguage={setLanguage}
        themeColors={themeColors}
        cardStyle={cardStyle}
        t={t}
      />

      {/* Main Content */}
      <main style={{ flex: 1, padding: '24px', overflow: 'auto', display: 'flex', gap: '24px' }}>
        <AnimatePresence mode="wait">
          {/* Chat Tab */}
          {activeTab === 'chat' && (
            <ChatTab
              messages={messages}
              inputMessage={inputMessage}
              isLoading={isLoading}
              selectedDocuments={selectedDocuments}
              sessionDocuments={sessionDocuments}
              suggestedQuestions={suggestedQuestions}
              showPasteModal={showPasteModal}
              pasteContent={pasteContent}
              pasteTitle={pasteTitle}
              uploadingSessionDoc={uploadingSessionDoc}
              dragOver={dragOver}
              externalConnections={externalConnections}
              availableResources={availableResources}
              showExternalModal={showExternalModal}
              connectingResource={connectingResource}
              syncingConnection={syncingConnection}
              clipboardContent={clipboardContent}
              setInputMessage={setInputMessage}
              setSelectedSource={setSelectedSource}
              setShowSourcePanel={setShowSourcePanel}
              setShowPasteModal={setShowPasteModal}
              setPasteContent={setPasteContent}
              setPasteTitle={setPasteTitle}
              setShowExternalModal={setShowExternalModal}
              sendMessage={sendMessage}
              saveAIResponse={saveAIResponse}
              removeSessionDocument={removeSessionDocument}
              handleDragOver={handleDragOver}
              handleDragLeave={handleDragLeave}
              handleDrop={handleDrop}
              handleClipboardPaste={handleClipboardPaste}
              addClipboardToSession={addClipboardToSession}
              clearClipboardContent={clearClipboardContent}
              pasteSessionText={pasteSessionText}
              connectExternalResource={connectExternalResource}
              disconnectExternalResource={disconnectExternalResource}
              syncExternalResource={syncExternalResource}
              themeColors={themeColors}
              cardStyle={cardStyle}
              tabStyle={tabStyle}
              inputStyle={inputStyle}
              t={t}
            />
          )}

          {/* Documents Tab */}
          {activeTab === 'documents' && (
            <DocumentsTab
              documents={documents}
              selectedDocuments={selectedDocuments}
              showUploadModal={showUploadModal}
              uploadFile={uploadFile}
              uploadSettings={uploadSettings}
              uploading={uploading}
              uploadProgress={uploadProgress}
              setSelectedDocuments={setSelectedDocuments}
              setShowUploadModal={setShowUploadModal}
              setUploadFile={setUploadFile}
              setUploadSettings={setUploadSettings}
              handleFileSelect={handleFileSelect}
              uploadDocument={uploadDocument}
              themeColors={themeColors}
              cardStyle={cardStyle}
              tabStyle={tabStyle}
              t={t}
            />
          )}

          {/* Web Sources Tab */}
          {activeTab === 'web-sources' && (
            <WebSourcesTab
              webSources={webSources}
              showAddUrlModal={showAddUrlModal}
              newUrls={newUrls}
              webSourceTags={webSourceTags}
              addingUrls={addingUrls}
              setShowAddUrlModal={setShowAddUrlModal}
              setNewUrls={setNewUrls}
              setWebSourceTags={setWebSourceTags}
              addWebSources={addWebSources}
              refreshWebSource={refreshWebSource}
              deleteWebSource={deleteWebSource}
              themeColors={themeColors}
              cardStyle={cardStyle}
              tabStyle={tabStyle}
              inputStyle={inputStyle}
              t={t}
            />
          )}

          {/* Notes Tab */}
          {activeTab === 'notes' && (
            <NotesTab
              notes={notes}
              folders={folders}
              selectedFolder={selectedFolder}
              selectedNote={selectedNote}
              searchQuery={searchQuery}
              noteTitle={noteTitle}
              noteContent={noteContent}
              setSelectedFolder={setSelectedFolder}
              setSelectedNote={setSelectedNote}
              setSearchQuery={setSearchQuery}
              setNoteTitle={setNoteTitle}
              setNoteContent={setNoteContent}
              handleSearch={handleSearch}
              createNote={createNote}
              themeColors={themeColors}
              cardStyle={cardStyle}
              tabStyle={tabStyle}
              t={t}
            />
          )}

          {/* Content Tab */}
          {activeTab === 'content' && (
            <ContentTab
              selectedDocuments={selectedDocuments}
              contents={contents}
              generatingContent={generatingContent}
              selectedContent={selectedContent}
              contentData={contentData}
              setSelectedContent={setSelectedContent}
              generateContent={generateContent}
              loadContentDetail={loadContentDetail}
              themeColors={themeColors}
              cardStyle={cardStyle}
              t={t}
            />
          )}

          {/* Projects Tab */}
          {activeTab === 'projects' && (
            <ProjectsTab
              projects={projects}
              selectedProject={selectedProject}
              setSelectedProject={setSelectedProject}
              createProject={createProject}
              themeColors={themeColors}
              cardStyle={cardStyle}
              tabStyle={tabStyle}
              t={t}
            />
          )}

          {/* Knowledge Graph Tab */}
          {activeTab === 'knowledge-graph' && (
            <KnowledgeGraphTab
              selectedDocuments={selectedDocuments}
              kgQuery={kgQuery}
              selectedKG={selectedKG}
              buildingKG={buildingKG}
              queryingKG={queryingKG}
              knowledgeGraphs={knowledgeGraphs}
              kgAnswer={kgAnswer}
              setKgQuery={setKgQuery}
              setSelectedKG={setSelectedKG}
              buildKnowledgeGraph={buildKnowledgeGraph}
              queryKnowledgeGraph={queryKnowledgeGraph}
              deleteKnowledgeGraph={deleteKnowledgeGraph}
              getEntityColor={getEntityColor}
              themeColors={themeColors}
              cardStyle={cardStyle}
              tabStyle={tabStyle}
              t={t}
            />
          )}

          {/* Knowledge Articles Tab */}
          {activeTab === 'knowledge-articles' && (
            <KnowledgeArticlesTab
              knowledgeArticles={knowledgeArticles}
              selectedArticle={selectedArticle}
              pendingReviews={pendingReviews}
              topContributors={topContributors}
              categories={categories}
              showCreateArticle={showCreateArticle}
              articleLanguage={articleLanguage}
              reviewComment={reviewComment}
              newArticle={newArticle}
              savingArticle={savingArticle}
              setSelectedArticle={setSelectedArticle}
              setShowCreateArticle={setShowCreateArticle}
              setArticleLanguage={setArticleLanguage}
              setReviewComment={setReviewComment}
              setNewArticle={setNewArticle}
              getStatusColor={getStatusColor}
              getStatusLabel={getStatusLabel}
              recommendArticle={recommendArticle}
              reviewArticle={reviewArticle}
              createKnowledgeArticle={createKnowledgeArticle}
              themeColors={themeColors}
              cardStyle={cardStyle}
              tabStyle={tabStyle}
              user={user}
              t={t}
            />
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
