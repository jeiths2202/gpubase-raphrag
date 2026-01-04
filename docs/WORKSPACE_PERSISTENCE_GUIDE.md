# Persistent AI Workspace - Implementation Guide

## Overview

This document describes the complete persistent workspace system for the Enterprise AI KMS platform.

**Key Features:**
- ✅ Persist ALL user activities across sessions
- ✅ Restore exact UI state after re-login
- ✅ Support 9 different menu types
- ✅ Multi-device continuity
- ✅ Automatic state synchronization
- ✅ Enterprise-grade audit trail

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    FRONTEND (React)                         │
│  ┌──────────────────────────────────────────────────────┐  │
│  │ WorkspaceStore (Zustand)                             │  │
│  │  - Auto-save with debounce                           │  │
│  │  - Optimistic updates                                │  │
│  │  - State restoration on login                        │  │
│  └─────────────┬────────────────────────────────────────┘  │
└────────────────┼─────────────────────────────────────────────┘
                 │ HTTP (REST API)
┌────────────────┼─────────────────────────────────────────────┐
│                ▼         BACKEND (FastAPI)                   │
│  ┌──────────────────────────────────────────────────────┐  │
│  │ Workspace Router                                     │  │
│  │  - /workspace/state/load  (restore)                  │  │
│  │  - /workspace/state/save  (persist menu)             │  │
│  │  - /workspace/graph/save  (persist graph)            │  │
│  │  - /workspace/session     (update session)           │  │
│  └──────────────┬───────────────────────────────────────┘  │
│                 │                                            │
│  ┌──────────────▼───────────────────────────────────────┐  │
│  │ WorkspaceService                                     │  │
│  │  - Business logic                                    │  │
│  │  - Transaction management                            │  │
│  │  - State validation                                  │  │
│  └──────────────┬───────────────────────────────────────┘  │
└─────────────────┼────────────────────────────────────────────┘
                  │
┌─────────────────▼────────────────────────────────────────────┐
│                 PostgreSQL Database                          │
│  ┌──────────────────────────────────────────────────────┐  │
│  │ Tables:                                              │  │
│  │  - conversations        (RAG chat history)           │  │
│  │  - messages            (individual messages)         │  │
│  │  - menu_states         (UI state per menu)           │  │
│  │  - graph_states        (mindmap/KG states)           │  │
│  │  - workspace_sessions  (user session context)        │  │
│  │  - user_documents      (document library)            │  │
│  └──────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────────┘
```

---

## Database Schema

See `migrations/001_workspace_persistence.sql` for complete DDL.

**Key Design Decisions:**

1. **JSONB for Flexibility**
   - Menu states use JSONB for schema-less storage
   - Allows adding new state fields without migrations
   - Still performant with proper indexes

2. **One State Per User Per Menu**
   - UNIQUE constraint on (user_id, menu_type)
   - Prevents duplicate states
   - Simplifies upsert operations

3. **Conversation Branching Support**
   - `parent_conversation_id` for fork tracking
   - `fork_point_message_id` for branch points
   - Future-proof for advanced features

4. **Audit Trail**
   - All tables have `created_at` and `updated_at`
   - Message versioning for regenerate
   - Token tracking for cost analysis

---

## Backend API

### 1. Load Workspace State (PRIMARY ENDPOINT)

```http
GET /api/v1/workspace/state/load
Authorization: Bearer <token>
```

**Response:**
```json
{
  "success": true,
  "data": {
    "menu_states": {
      "chat": {
        "activeConversationId": "uuid-123",
        "scrollPosition": 420
      },
      "documents": {
        "selectedDocuments": ["doc1", "doc2"]
      }
    },
    "graph_states": {
      "mindmap": [...],
      "knowledge_graph": [...]
    },
    "recent_conversations": [...],
    "session": {
      "last_active_menu": "chat",
      "preferences": {...}
    },
    "last_active_menu": "chat",
    "last_conversation_id": "uuid-123"
  }
}
```

**When to Call:**
- User login
- App initialization
- After session timeout recovery

---

### 2. Save Menu State

```http
POST /api/v1/workspace/state/save
Content-Type: application/json
Authorization: Bearer <token>

{
  "menu_type": "chat",
  "state": {
    "activeConversationId": "uuid-123",
    "scrollPosition": 420,
    "filterSettings": {"archived": false}
  }
}
```

**When to Call:**
- Automatically on state change (debounced)
- Before navigation
- On window/tab close (beforeunload)
- Manually via "Save" button

---

### 3. Save Graph State

```http
POST /api/v1/workspace/graph/save
Content-Type: application/json

{
  "graph_type": "mindmap",
  "graph_name": "GPU Architecture Overview",
  "state": {
    "nodes": [
      {"id": "n1", "label": "GPU", "x": 100, "y": 200}
    ],
    "edges": [
      {"source": "n1", "target": "n2", "label": "enables"}
    ],
    "viewport": {"zoom": 1.0, "centerX": 200, "centerY": 200}
  }
}
```

---

### 4. Update Workspace Session

```http
PUT /api/v1/workspace/session
Content-Type: application/json

{
  "last_active_menu": "documents",
  "preferences": {
    "theme": "dark",
    "language": "ko",
    "auto_save_interval": 3000
  }
}
```

---

## Frontend Integration

### 1. App Initialization

```typescript
// App.tsx
import { useWorkspaceStore } from './store/workspaceStore';
import { useEffect } from 'react';

function App() {
  const initializeWorkspace = useWorkspaceStore(state => state.initializeWorkspace);
  const isRestoring = useWorkspaceStore(state => state.isRestoring);
  const activeMenu = useWorkspaceStore(state => state.activeMenu);

  useEffect(() => {
    // Initialize workspace on app mount
    initializeWorkspace();
  }, [initializeWorkspace]);

  if (isRestoring) {
    return <LoadingScreen message="Restoring workspace..." />;
  }

  return (
    <Layout>
      <MenuNavigation activeMenu={activeMenu} />
      <Routes>
        <Route path="/chat" element={<ChatMenu />} />
        <Route path="/documents" element={<DocumentsMenu />} />
        {/* ... other routes */}
      </Routes>
    </Layout>
  );
}
```

---

### 2. Using Menu State (Chat Example)

```typescript
// ChatMenu.tsx
import { useWorkspaceStore, useMenuState, useSetMenuState } from '../store/workspaceStore';

interface ChatMenuState {
  activeConversationId: string | null;
  scrollPosition: number;
  filterSettings: {
    archived: boolean;
    dateRange: string;
  };
}

function ChatMenu() {
  // Get chat menu state
  const chatState = useMenuState<ChatMenuState>('chat');
  const setChatState = useSetMenuState('chat');

  // Access specific fields
  const activeConversationId = chatState.activeConversationId;
  const scrollPosition = chatState.scrollPosition || 0;

  // Update state (auto-saved with debounce)
  const handleConversationSelect = (conversationId: string) => {
    setChatState({ activeConversationId: conversationId });
  };

  const handleScroll = (position: number) => {
    setChatState({ scrollPosition: position });
  };

  return (
    <div>
      <ConversationList
        activeId={activeConversationId}
        onSelect={handleConversationSelect}
        scrollPosition={scrollPosition}
        onScroll={handleScroll}
      />
      {activeConversationId && (
        <ConversationView conversationId={activeConversationId} />
      )}
    </div>
  );
}
```

---

### 3. Using Graph State (Mindmap Example)

```typescript
// MindmapMenu.tsx
import { useWorkspaceStore } from '../store/workspaceStore';

function MindmapMenu() {
  const saveGraphState = useWorkspaceStore(state => state.saveGraphState);
  const graphStates = useWorkspaceStore(state => state.graphStates.mindmap);

  const [currentGraph, setCurrentGraph] = useState({
    nodes: [],
    edges: [],
    viewport: { zoom: 1.0, centerX: 0, centerY: 0 }
  });

  // Save on graph modification
  const handleNodeMove = (nodeId: string, x: number, y: number) => {
    const updatedGraph = {
      ...currentGraph,
      nodes: currentGraph.nodes.map(n =>
        n.id === nodeId ? { ...n, x, y } : n
      )
    };

    setCurrentGraph(updatedGraph);

    // Auto-save to backend (debounced internally)
    saveGraphState('mindmap', 'My Mindmap', updatedGraph);
  };

  return (
    <MindmapCanvas
      graph={currentGraph}
      onNodeMove={handleNodeMove}
    />
  );
}
```

---

### 4. Workspace Preferences

```typescript
// SettingsMenu.tsx
import { useWorkspaceStore } from '../store/workspaceStore';

function SettingsMenu() {
  const session = useWorkspaceStore(state => state.session);
  const updatePreferences = useWorkspaceStore(state => state.updatePreferences);

  const preferences = session?.preferences || {};

  const handleThemeChange = async (theme: 'light' | 'dark' | 'auto') => {
    await updatePreferences({ theme });
  };

  return (
    <div>
      <ThemePicker value={preferences.theme} onChange={handleThemeChange} />
      <LanguagePicker value={preferences.language} onChange={lang => updatePreferences({ language: lang })} />
      <AutoSaveInterval value={preferences.auto_save_interval} onChange={interval => updatePreferences({ auto_save_interval: interval })} />
    </div>
  );
}
```

---

## State Persistence Patterns

### Pattern 1: Auto-Save on Every Change

```typescript
// Automatically persists with debounce (5 seconds default)
const setChatState = useSetMenuState('chat');

// This will trigger auto-save after 5 seconds of no changes
setChatState({ scrollPosition: 100 });
setChatState({ scrollPosition: 200 }); // Cancels previous save
setChatState({ scrollPosition: 300 }); // Only this will be saved (after 5s)
```

---

### Pattern 2: Manual Save

```typescript
// Disable auto-save for fine control
const disableAutoSave = useWorkspaceStore(state => state.disableAutoSave);
const saveMenuState = useWorkspaceStore(state => state.saveMenuState);

useEffect(() => {
  disableAutoSave();
  return () => enableAutoSave();
}, []);

// Manually trigger save
const handleSaveClick = async () => {
  await saveMenuState('chat');
  toast.success('Chat state saved!');
};
```

---

### Pattern 3: Save on Navigation

```typescript
// Save all states before navigation
const saveAllMenuStates = useWorkspaceStore(state => state.saveAllMenuStates);

const handleNavigate = async (newMenu: MenuType) => {
  await saveAllMenuStates(); // Ensure all changes persisted
  navigate(`/${newMenu}`);
};
```

---

### Pattern 4: Save on Window Close

```typescript
// Ensure state persisted before user leaves
useEffect(() => {
  const handleBeforeUnload = async (e: BeforeUnloadEvent) => {
    const pendingSaves = useWorkspaceStore.getState().pendingSaves;

    if (pendingSaves.size > 0) {
      e.preventDefault();
      e.returnValue = '';
      await useWorkspaceStore.getState().saveAllMenuStates();
    }
  };

  window.addEventListener('beforeunload', handleBeforeUnload);
  return () => window.removeEventListener('beforeunload', handleBeforeUnload);
}, []);
```

---

## Menu State Schema Examples

### Chat Menu

```typescript
{
  activeConversationId: "uuid-123",
  scrollPosition: 420,
  filterSettings: {
    archived: false,
    dateRange: "7days",
    searchQuery: ""
  },
  viewMode: "list",
  sidebarWidth: 300,
  sortBy: "updated_at"
}
```

### Documents Menu

```typescript
{
  selectedDocuments: ["doc1", "doc2"],
  filterSettings: {
    type: "pdf",
    tags: ["research", "gpu"],
    favorite: false
  },
  sortBy: "title",
  viewMode: "grid",
  previewPanelOpen: true
}
```

### Mindmap Menu

```typescript
{
  activeGraphId: "uuid-456",
  viewportState: {
    zoom: 1.5,
    centerX: 200,
    centerY: 300
  },
  selectedNodes: ["node1", "node2"],
  editMode: true,
  layoutAlgorithm: "force-directed"
}
```

---

## Best Practices

### 1. State Granularity

✅ **DO**: Store user-specific UI preferences
```typescript
{ scrollPosition: 420, sidebarWidth: 300, viewMode: "grid" }
```

❌ **DON'T**: Store derived or computed state
```typescript
{ totalMessages: 42 } // Compute this from message count
```

---

### 2. State Size Optimization

✅ **DO**: Store minimal identifiers
```typescript
{ selectedDocuments: ["doc1", "doc2"] } // Just IDs
```

❌ **DON'T**: Store entire objects
```typescript
{ selectedDocuments: [{id, title, content, ...}] } // Too large
```

---

### 3. Sensitive Data

✅ **DO**: Store non-sensitive UI state
```typescript
{ theme: "dark", language: "en" }
```

❌ **DON'T**: Store sensitive user data in state
```typescript
{ creditCardNumber: "1234..." } // Use separate secure storage
```

---

### 4. Auto-Save Tuning

```typescript
// For frequent updates (e.g., canvas drawing)
updatePreferences({ auto_save_interval: 10000 }); // 10 seconds

// For infrequent updates (e.g., settings)
updatePreferences({ auto_save_interval: 1000 }); // 1 second
```

---

## Testing

### Unit Tests (Backend)

```python
# tests/test_workspace_service.py
async def test_save_and_load_menu_state():
    service = WorkspaceService()
    user_id = uuid4()

    # Save state
    menu_state = MenuStateSave(
        menu_type="chat",
        state={"activeConversationId": "uuid-123"}
    )
    saved = await service.save_menu_state(user_id, menu_state)

    assert saved.state["activeConversationId"] == "uuid-123"

    # Load state
    loaded = await service.get_menu_state(user_id, "chat")
    assert loaded.state == saved.state
```

### Integration Tests (Frontend)

```typescript
// tests/workspace.test.tsx
import { renderHook, act } from '@testing-library/react';
import { useWorkspaceStore } from '../store/workspaceStore';

test('should persist and restore menu state', async () => {
  const { result } = renderHook(() => useWorkspaceStore());

  // Set menu state
  act(() => {
    result.current.setMenuState('chat', { activeConversationId: 'uuid-123' });
  });

  // Save
  await act(async () => {
    await result.current.saveMenuState('chat');
  });

  // Clear store
  act(() => {
    result.current.clearWorkspace();
  });

  // Restore
  await act(async () => {
    await result.current.initializeWorkspace();
  });

  // Verify state restored
  const chatState = result.current.menuStates.chat;
  expect(chatState.activeConversationId).toBe('uuid-123');
});
```

---

## Migration from localStorage

If you're currently using localStorage:

```typescript
// Before (localStorage)
localStorage.setItem('chatState', JSON.stringify({ activeConversationId: 'uuid' }));
const chatState = JSON.parse(localStorage.getItem('chatState') || '{}');

// After (Persistent Workspace)
const setChatState = useSetMenuState('chat');
setChatState({ activeConversationId: 'uuid' });
const chatState = useMenuState('chat');
```

**Benefits of migration:**
- ✅ Multi-device sync
- ✅ Server-side backup
- ✅ No 5MB localStorage limit
- ✅ Automatic conflict resolution
- ✅ Audit trail and versioning

---

## Performance Considerations

1. **Debounced Saves**: Auto-save uses 5-second debounce to batch updates
2. **Optimistic Updates**: UI updates immediately, backend sync happens asynchronously
3. **JSONB Indexing**: PostgreSQL GIN indexes on JSONB fields for fast queries
4. **Connection Pooling**: Reuse database connections for efficiency
5. **Lazy Loading**: Only load active menu states, defer others

---

## Security Considerations

1. **Authentication**: All endpoints require valid JWT token
2. **Authorization**: Users can only access their own workspace state
3. **Input Validation**: Pydantic models validate all state data
4. **SQL Injection**: Parameterized queries prevent injection attacks
5. **Rate Limiting**: Implement rate limits on save endpoints to prevent abuse

---

## Future Enhancements

1. **Conversation Branching**: Implement fork/branch UI for conversation trees
2. **Prompt Versioning**: Track prompt templates and A/B test results
3. **Collaborative Workspaces**: Share workspace states between team members
4. **Conflict Resolution**: Handle simultaneous updates from multiple devices
5. **State History**: Add undo/redo with state snapshots
6. **Export/Import**: Allow users to export/import workspace configurations

---

## Troubleshooting

### State not persisting

1. Check network tab for 401 (authentication issue)
2. Verify auto-save is enabled: `useWorkspaceStore.getState().autoSaveEnabled`
3. Check pending saves: `useWorkspaceStore.getState().pendingSaves`

### State not restoring on login

1. Check `initializeWorkspace()` is called in App component
2. Verify backend returns data: `/api/v1/workspace/state/load`
3. Check browser console for errors during restoration

### Performance issues

1. Increase auto-save interval for frequently changing state
2. Use manual save for large graph states
3. Optimize JSONB state size (remove unnecessary fields)

---

## Summary

The Persistent AI Workspace system provides enterprise-grade state management with:

- **Flexibility**: JSONB storage for any menu-specific state
- **Reliability**: PostgreSQL ensures data durability
- **Performance**: Debounced auto-save and optimistic updates
- **Scalability**: Designed for multi-device, multi-user scenarios
- **Security**: Authentication, authorization, and input validation

By following this guide, you can seamlessly integrate persistent state management into your AI KMS application.
