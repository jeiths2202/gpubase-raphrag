import React, { useState, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { useNavigate } from 'react-router-dom';
import { useAuthStore } from '../store/authStore';

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

type TabType = 'chat' | 'documents' | 'notes' | 'content' | 'projects' | 'mindmap' | 'knowledge-graph';
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

  // Source panel state
  const [showSourcePanel, setShowSourcePanel] = useState(false);
  const [selectedSource, setSelectedSource] = useState<any>(null);

  // Sidebar state
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);

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

  // Load initial data
  useEffect(() => {
    loadProjects();
    loadDocuments();
    loadConversations();
  }, []);

  useEffect(() => {
    if (activeTab === 'notes') {
      loadNotes();
      loadFolders();
    } else if (activeTab === 'content') {
      loadContents();
    } else if (activeTab === 'knowledge-graph') {
      loadKnowledgeGraphs();
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
      const res = await fetch(`${API_BASE}/query`, {
        method: 'POST',
        headers: getAuthHeaders(),
        body: JSON.stringify({
          question: inputMessage,
          strategy: 'auto',
          language: 'auto',
          options: {
            top_k: 5,
            include_sources: true,
            conversation_id: selectedConversation
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
          score: s.score
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
    // Mock suggested questions - in production, this would use LLM
    const suggestions = [
      `${query}에 대해 더 자세히 알려주세요`,
      '관련된 예시를 보여주세요',
      '이 주제의 장단점은 무엇인가요?'
    ];
    setSuggestedQuestions(suggestions);
  };

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
          overflow: 'hidden'
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

        {/* User Info */}
        {!sidebarCollapsed && (
          <div style={{ padding: '12px', background: 'rgba(255,255,255,0.05)', borderRadius: '8px' }}>
            <div style={{ fontWeight: 600 }}>{user?.username || 'User'}</div>
            <div style={{ fontSize: '12px', color: themeColors.textSecondary }}>{user?.email}</div>
          </div>
        )}

        {/* Navigation Tabs */}
        <nav style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
          {[
            { key: 'chat', label: 'Chat', icon: '💬' },
            { key: 'documents', label: 'Documents', icon: '📄' },
            { key: 'notes', label: 'Notes', icon: '📝' },
            { key: 'content', label: 'AI Content', icon: '🤖' },
            { key: 'projects', label: 'Projects', icon: '📁' },
            { key: 'mindmap', label: 'Mindmap', icon: '🧠' },
            { key: 'knowledge-graph', label: 'Knowledge Graph', icon: '🔗' }
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
              {!sidebarCollapsed && <span>{tab.label}</span>}
            </button>
          ))}
        </nav>

        {/* Projects List */}
        {!sidebarCollapsed && activeTab !== 'projects' && (
          <div style={{ flex: 1, overflow: 'auto' }}>
            <h3 style={{ fontSize: '14px', color: themeColors.textSecondary, marginBottom: '8px' }}>Projects</h3>
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
            {!sidebarCollapsed && <span>{theme === 'dark' ? 'Dark' : 'Light'}</span>}
          </button>
          {user?.role === 'admin' && (
            <button
              onClick={() => navigate('/admin')}
              style={{ ...tabStyle(false), display: 'flex', alignItems: 'center', gap: '12px', justifyContent: sidebarCollapsed ? 'center' : 'flex-start' }}
            >
              <span>⚙️</span>
              {!sidebarCollapsed && <span>Admin</span>}
            </button>
          )}
          <button
            onClick={logout}
            style={{ ...tabStyle(false), display: 'flex', alignItems: 'center', gap: '12px', justifyContent: sidebarCollapsed ? 'center' : 'flex-start' }}
          >
            <span>🚪</span>
            {!sidebarCollapsed && <span>Logout</span>}
          </button>
        </div>
      </motion.aside>

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
                <h2 style={{ margin: 0 }}>AI Chat</h2>
                <p style={{ color: themeColors.textSecondary, margin: '8px 0 0' }}>
                  문서 기반 AI 질의응답 - 선택된 문서: {selectedDocuments.length}개
                </p>
              </div>

              {/* Messages */}
              <div style={{ ...cardStyle, flex: 1, overflow: 'auto', display: 'flex', flexDirection: 'column', gap: '16px' }}>
                {messages.length === 0 ? (
                  <div style={{ textAlign: 'center', padding: '40px', color: themeColors.textSecondary }}>
                    <p>질문을 입력하여 대화를 시작하세요.</p>
                    <div style={{ display: 'flex', flexWrap: 'wrap', gap: '8px', justifyContent: 'center', marginTop: '16px' }}>
                      {['문서 요약해줘', '핵심 개념은?', '예시를 보여줘'].map((q, i) => (
                        <button
                          key={i}
                          onClick={() => setInputMessage(q)}
                          style={{ ...tabStyle(false), fontSize: '14px' }}
                        >
                          {q}
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
                            출처 ({msg.sources.length}개):
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

              {/* Input */}
              <div style={{ ...cardStyle, display: 'flex', gap: '12px' }}>
                <input
                  type="text"
                  value={inputMessage}
                  onChange={(e) => setInputMessage(e.target.value)}
                  onKeyPress={(e) => e.key === 'Enter' && sendMessage()}
                  placeholder="질문을 입력하세요..."
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
                  전송
                </button>
              </div>
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
