/**
 * Artifact Panel Component
 *
 * Displays code artifacts, markdown, and other generated content
 * in a resizable right-side panel.
 *
 * Security: Uses DOMPurify to sanitize all HTML content before rendering.
 */

import { useState, useEffect, useRef, useCallback } from 'react';
import {
  X,
  Copy,
  Check,
  Download,
  Maximize2,
  Minimize2,
  Code2,
  FileText,
  FileCode,
  FileJson,
  GitCompare,
  Terminal,
  Hash,
  Clock,
} from 'lucide-react';
import { codeToHtml, type BundledLanguage, type BundledTheme } from 'shiki';
import DOMPurify from 'dompurify';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { useArtifactStore, type Artifact } from '../store/artifactStore';
import type { ArtifactType } from '../api/agent.api';
import './ArtifactPanel.css';

// =============================================================================
// Constants
// =============================================================================

const MIN_PANEL_WIDTH = 300;
const MAX_PANEL_WIDTH = 1200;

// Map artifact types to icons
const ARTIFACT_TYPE_ICONS: Record<ArtifactType, React.ElementType> = {
  code: Code2,
  text: FileText,
  markdown: FileCode,
  html: FileCode,
  json: FileJson,
  diff: GitCompare,
  log: Terminal,
  image: FileText,
};

// Map languages to Shiki bundled languages
const LANGUAGE_MAP: Record<string, BundledLanguage> = {
  python: 'python',
  javascript: 'javascript',
  typescript: 'typescript',
  java: 'java',
  go: 'go',
  rust: 'rust',
  c: 'c',
  cpp: 'cpp',
  csharp: 'csharp',
  ruby: 'ruby',
  php: 'php',
  swift: 'swift',
  kotlin: 'kotlin',
  sql: 'sql',
  bash: 'bash',
  powershell: 'powershell',
  html: 'html',
  css: 'css',
  scss: 'scss',
  json: 'json',
  yaml: 'yaml',
  xml: 'xml',
  toml: 'toml',
  markdown: 'markdown',
  dockerfile: 'dockerfile',
  diff: 'diff',
};

// Configure DOMPurify for safe HTML rendering
const PURIFY_CONFIG = {
  ALLOWED_TAGS: ['pre', 'code', 'span', 'div', 'br'],
  ALLOWED_ATTR: ['class', 'style'],
};

// =============================================================================
// Component
// =============================================================================

export function ArtifactPanel() {
  const {
    panel,
    closePanel,
    setPanelWidth,
    selectArtifact,
    removeArtifact,
    getSelectedArtifact,
    getCurrentArtifacts,
    currentAgentType,
  } = useArtifactStore();

  // Get artifacts for the current agent
  const artifacts = getCurrentArtifacts();

  const [isDragging, setIsDragging] = useState(false);
  const [isFullscreen, setIsFullscreen] = useState(false);
  const [copiedId, setCopiedId] = useState<string | null>(null);
  const [highlightedCode, setHighlightedCode] = useState<string>('');
  const [isHighlighting, setIsHighlighting] = useState(false);

  const panelRef = useRef<HTMLDivElement>(null);
  const dragStartX = useRef(0);
  const dragStartWidth = useRef(0);

  const selectedArtifact = getSelectedArtifact();

  // Highlight code using Shiki with DOMPurify sanitization
  useEffect(() => {
    if (!selectedArtifact || selectedArtifact.type !== 'code') {
      setHighlightedCode('');
      return;
    }

    const highlightCode = async () => {
      setIsHighlighting(true);
      try {
        const language = LANGUAGE_MAP[selectedArtifact.language || ''] || 'text';
        const theme: BundledTheme = document.documentElement.dataset.theme === 'light'
          ? 'github-light'
          : 'github-dark';

        const html = await codeToHtml(selectedArtifact.content, {
          lang: language,
          theme,
        });

        // Sanitize Shiki output with DOMPurify
        const sanitizedHtml = DOMPurify.sanitize(html, PURIFY_CONFIG);
        setHighlightedCode(sanitizedHtml);
      } catch (error) {
        console.warn('Shiki highlighting failed:', error);
        // Fallback: escape HTML manually and wrap in pre/code
        const escaped = escapeHtml(selectedArtifact.content);
        setHighlightedCode(`<pre><code>${escaped}</code></pre>`);
      } finally {
        setIsHighlighting(false);
      }
    };

    highlightCode();
  }, [selectedArtifact?.id, selectedArtifact?.content, selectedArtifact?.language]);

  // Handle resize drag
  const handleMouseDown = useCallback((e: React.MouseEvent) => {
    e.preventDefault();
    setIsDragging(true);
    dragStartX.current = e.clientX;
    dragStartWidth.current = panel.width;
  }, [panel.width]);

  useEffect(() => {
    if (!isDragging) return;

    const handleMouseMove = (e: MouseEvent) => {
      const delta = dragStartX.current - e.clientX;
      const newWidth = Math.max(
        MIN_PANEL_WIDTH,
        Math.min(MAX_PANEL_WIDTH, dragStartWidth.current + delta)
      );
      setPanelWidth(newWidth);
    };

    const handleMouseUp = () => {
      setIsDragging(false);
    };

    document.addEventListener('mousemove', handleMouseMove);
    document.addEventListener('mouseup', handleMouseUp);

    return () => {
      document.removeEventListener('mousemove', handleMouseMove);
      document.removeEventListener('mouseup', handleMouseUp);
    };
  }, [isDragging, setPanelWidth]);

  // Copy to clipboard
  const handleCopy = useCallback(async () => {
    if (!selectedArtifact) return;

    try {
      await navigator.clipboard.writeText(selectedArtifact.content);
      setCopiedId(selectedArtifact.id);
      setTimeout(() => setCopiedId(null), 2000);
    } catch (error) {
      console.error('Copy failed:', error);
    }
  }, [selectedArtifact]);

  // Download artifact
  const handleDownload = useCallback(() => {
    if (!selectedArtifact) return;

    const extension = getFileExtension(selectedArtifact.type, selectedArtifact.language);
    const filename = `${selectedArtifact.title.replace(/[^a-z0-9]/gi, '_')}${extension}`;
    const blob = new Blob([selectedArtifact.content], { type: 'text/plain' });
    const url = URL.createObjectURL(blob);

    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    a.click();

    URL.revokeObjectURL(url);
  }, [selectedArtifact]);

  // Toggle fullscreen
  const handleFullscreen = useCallback(() => {
    setIsFullscreen((prev) => !prev);
  }, []);

  // Format time
  const formatTime = (date: Date) => {
    return new Intl.DateTimeFormat('default', {
      hour: '2-digit',
      minute: '2-digit',
    }).format(date);
  };

  // Don't render if panel is closed
  if (!panel.isOpen) {
    return null;
  }

  const TypeIcon = selectedArtifact
    ? ARTIFACT_TYPE_ICONS[selectedArtifact.type] || FileText
    : FileText;

  return (
    <div
      ref={panelRef}
      className={`artifact-panel ${isFullscreen ? 'fullscreen' : ''}`}
      style={{ width: isFullscreen ? undefined : panel.width }}
    >
      {/* Resize Handle */}
      {!isFullscreen && (
        <div
          className={`artifact-panel-resize-handle ${isDragging ? 'dragging' : ''}`}
          onMouseDown={handleMouseDown}
        />
      )}

      {/* Header */}
      <div className="artifact-panel-header">
        <div className="artifact-panel-title">
          {selectedArtifact ? (
            <>
              <TypeIcon size={16} />
              <h3>{selectedArtifact.title}</h3>
              <span className={`artifact-badge type-${selectedArtifact.type}`}>
                {selectedArtifact.type}
              </span>
              {selectedArtifact.language && (
                <span className="artifact-badge language">
                  {selectedArtifact.language}
                </span>
              )}
            </>
          ) : (
            <h3>Artifacts</h3>
          )}
        </div>

        <div className="artifact-panel-actions">
          {selectedArtifact && (
            <>
              <button
                className={`artifact-action-btn ${copiedId === selectedArtifact.id ? 'copied' : ''}`}
                onClick={handleCopy}
                title="Copy to clipboard"
              >
                {copiedId === selectedArtifact.id ? <Check size={16} /> : <Copy size={16} />}
              </button>
              <button
                className="artifact-action-btn"
                onClick={handleDownload}
                title="Download"
              >
                <Download size={16} />
              </button>
              <button
                className="artifact-action-btn"
                onClick={handleFullscreen}
                title={isFullscreen ? 'Exit fullscreen' : 'Fullscreen'}
              >
                {isFullscreen ? <Minimize2 size={16} /> : <Maximize2 size={16} />}
              </button>
            </>
          )}
          <button
            className="artifact-action-btn close"
            onClick={closePanel}
            title="Close panel"
          >
            <X size={16} />
          </button>
        </div>
      </div>

      {/* Tabs (when multiple artifacts) */}
      {artifacts.length > 1 && (
        <div className="artifact-tabs">
          {artifacts.map((artifact) => {
            const Icon = ARTIFACT_TYPE_ICONS[artifact.type] || FileText;
            return (
              <button
                key={artifact.id}
                className={`artifact-tab ${artifact.id === panel.selectedArtifactId ? 'active' : ''}`}
                onClick={() => selectArtifact(artifact.id)}
              >
                <span className="artifact-tab-icon">
                  <Icon size={14} />
                </span>
                <span>{truncateTitle(artifact.title, 20)}</span>
                <span
                  className="artifact-tab-close"
                  onClick={(e) => {
                    e.stopPropagation();
                    removeArtifact(currentAgentType, artifact.id);
                  }}
                >
                  <X size={12} />
                </span>
              </button>
            );
          })}
        </div>
      )}

      {/* Content */}
      <div className="artifact-content">
        {isHighlighting ? (
          <div className="artifact-loading">
            <div className="artifact-loading-spinner" />
          </div>
        ) : selectedArtifact ? (
          <ArtifactContent artifact={selectedArtifact} highlightedCode={highlightedCode} />
        ) : (
          <div className="artifact-empty">
            <div className="artifact-empty-icon">
              <Code2 size={28} />
            </div>
            <h4>No artifact selected</h4>
            <p>Generated code and documents will appear here</p>
          </div>
        )}
      </div>

      {/* Footer */}
      {selectedArtifact && (
        <div className="artifact-footer">
          <div className="artifact-metadata">
            <span className="artifact-metadata-item">
              <Hash size={12} />
              {selectedArtifact.lineCount} lines
            </span>
            <span className="artifact-metadata-item">
              {selectedArtifact.charCount.toLocaleString()} chars
            </span>
          </div>
          <span className="artifact-metadata-item">
            <Clock size={12} />
            {formatTime(selectedArtifact.createdAt)}
          </span>
        </div>
      )}
    </div>
  );
}

// =============================================================================
// Sub-components
// =============================================================================

interface ArtifactContentProps {
  artifact: Artifact;
  highlightedCode: string;
}

function ArtifactContent({ artifact, highlightedCode }: ArtifactContentProps) {
  switch (artifact.type) {
    case 'code':
      // highlightedCode is already sanitized by DOMPurify in the parent effect
      return (
        <div
          className="artifact-code-content"
          dangerouslySetInnerHTML={{ __html: highlightedCode }}
        />
      );

    case 'markdown':
      return (
        <div className="artifact-markdown-content">
          <ReactMarkdown remarkPlugins={[remarkGfm]}>
            {artifact.content}
          </ReactMarkdown>
        </div>
      );

    case 'json':
      return (
        <div className="artifact-code-content">
          <pre>
            <code>{formatJson(artifact.content)}</code>
          </pre>
        </div>
      );

    case 'diff':
      return (
        <div className="artifact-code-content artifact-diff-content">
          <pre>
            <code>{artifact.content}</code>
          </pre>
        </div>
      );

    case 'log':
    case 'text':
    default:
      return (
        <div className="artifact-text-content">
          {artifact.content}
        </div>
      );
  }
}

// =============================================================================
// Helper Functions
// =============================================================================

function getFileExtension(type: ArtifactType, language?: string): string {
  if (type === 'code' && language) {
    const extensions: Record<string, string> = {
      python: '.py',
      javascript: '.js',
      typescript: '.ts',
      java: '.java',
      go: '.go',
      rust: '.rs',
      c: '.c',
      cpp: '.cpp',
      csharp: '.cs',
      ruby: '.rb',
      php: '.php',
      swift: '.swift',
      kotlin: '.kt',
      sql: '.sql',
      bash: '.sh',
      powershell: '.ps1',
      html: '.html',
      css: '.css',
      scss: '.scss',
      json: '.json',
      yaml: '.yaml',
      xml: '.xml',
      toml: '.toml',
    };
    return extensions[language] || '.txt';
  }

  const typeExtensions: Record<ArtifactType, string> = {
    code: '.txt',
    text: '.txt',
    markdown: '.md',
    html: '.html',
    json: '.json',
    diff: '.diff',
    log: '.log',
    image: '.png',
  };

  return typeExtensions[type] || '.txt';
}

function truncateTitle(title: string, maxLength: number): string {
  if (title.length <= maxLength) return title;
  return title.substring(0, maxLength - 3) + '...';
}

function formatJson(content: string): string {
  try {
    const parsed = JSON.parse(content);
    return JSON.stringify(parsed, null, 2);
  } catch {
    return content;
  }
}

function escapeHtml(text: string): string {
  const div = document.createElement('div');
  div.textContent = text;
  return div.innerHTML;
}

export default ArtifactPanel;
