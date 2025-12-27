// NotesTab Component
// Extracted from KnowledgeApp.tsx - NO LOGIC CHANGES

import React from 'react';
import { motion } from 'framer-motion';
import type { ThemeColors, Note, Folder } from '../types';
import { TranslateFunction } from '../../../i18n/types';

interface NotesTabProps {
  // State
  notes: Note[];
  folders: Folder[];
  selectedFolder: string | null;
  selectedNote: Note | null;
  searchQuery: string;
  noteTitle: string;
  noteContent: string;

  // State setters
  setSelectedFolder: (folderId: string | null) => void;
  setSelectedNote: (note: Note | null) => void;
  setSearchQuery: (query: string) => void;
  setNoteTitle: (title: string) => void;
  setNoteContent: (content: string) => void;

  // Functions
  handleSearch: () => void;
  createNote: () => void;

  // Styles
  themeColors: ThemeColors;
  cardStyle: React.CSSProperties;
  tabStyle: (isActive: boolean) => React.CSSProperties;

  // i18n
  t: TranslateFunction;
}

export const NotesTab: React.FC<NotesTabProps> = ({
  notes,
  folders,
  selectedFolder,
  selectedNote,
  searchQuery,
  noteTitle,
  noteContent,
  setSelectedFolder,
  setSelectedNote,
  setSearchQuery,
  setNoteTitle,
  setNoteContent,
  handleSearch,
  createNote,
  themeColors,
  cardStyle,
  tabStyle,
  t: _t
}) => {
  // _t reserved for future i18n support
  return (
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
  );
};

export default NotesTab;
