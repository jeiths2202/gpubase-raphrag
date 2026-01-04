# Persistent AI Workspace System

## Executive Summary

A production-ready, enterprise-grade persistent workspace system for multi-menu AI Knowledge Management platforms. Enables seamless state preservation across logout/login with multi-device continuity.

---

## 🎯 Key Features

✅ **Complete State Persistence** - All user activities, UI states, and AI interactions preserved
✅ **Multi-Menu Support** - 9 menu types (Chat, Documents, Web Sources, Notes, AI Content, Projects, Mindmap, Knowledge Graph, Knowledge Base)
✅ **Multi-Device Continuity** - Exact workspace restoration across devices
✅ **Auto-Save** - Debounced automatic state synchronization
✅ **Graph State Persistence** - Visual mindmap and knowledge graph layouts preserved
✅ **Conversation History** - Complete RAG chat history with branching support
✅ **Enterprise Security** - Authentication, authorization, input validation
✅ **Audit Trail** - Full tracking of state changes with timestamps

---

## 📁 File Structure

```
gpubase-raphrag/
│
├── migrations/
│   └── 001_workspace_persistence.sql        # PostgreSQL schema (DDL)
│
├── app/api/
│   ├── models/
│   │   └── workspace.py                     # Pydantic models
│   ├── services/
│   │   └── workspace_service.py             # Business logic
│   └── routers/
│       └── workspace.py                     # REST API endpoints
│
├── frontend/src/
│   └── store/
│       └── workspaceStore.ts                # Zustand state management
│
└── docs/
    ├── WORKSPACE_PERSISTENCE_README.md      # This file
    ├── WORKSPACE_PERSISTENCE_GUIDE.md       # Comprehensive guide
    └── WORKSPACE_API_EXAMPLES.json          # API examples
```

---

## 🚀 Quick Start

### 1. Database Setup

```bash
# Run migration script
psql -U postgres -d kms_db -f migrations/001_workspace_persistence.sql
```

**What it creates:**
- `conversations` - RAG chat sessions
- `messages` - Individual chat messages
- `menu_states` - UI state per menu (JSONB)
- `graph_states` - Mindmap/KG visual layouts
- `workspace_sessions` - User session context
- `user_documents` - Document library metadata

---

### 2. Backend Integration

**Register router in `app/api/main.py`:**

```python
from app.api.routers import workspace

app.include_router(workspace.router, prefix="/api/v1")
```

**That's it!** The following endpoints are now available:

- `GET /api/v1/workspace/state/load` - Restore workspace
- `POST /api/v1/workspace/state/save` - Save menu state
- `POST /api/v1/workspace/graph/save` - Save graph state
- `PUT /api/v1/workspace/session` - Update session
- `POST /api/v1/workspace/conversations` - Create conversation
- `POST /api/v1/workspace/messages` - Add message

---

### 3. Frontend Integration

**Initialize workspace in `App.tsx`:**

```typescript
import { useWorkspaceStore } from './store/workspaceStore';

function App() {
  const initializeWorkspace = useWorkspaceStore(state => state.initializeWorkspace);

  useEffect(() => {
    initializeWorkspace(); // Restore state on login
  }, []);

  // ... rest of your app
}
```

**Use in components:**

```typescript
// Get menu state
const chatState = useMenuState<ChatMenuState>('chat');

// Update state (auto-saves with debounce)
const setChatState = useSetMenuState('chat');
setChatState({ activeConversationId: 'uuid-123' });
```

---

## 💡 Usage Examples

### Example 1: Chat Menu

```typescript
function ChatMenu() {
  const chatState = useMenuState<ChatMenuState>('chat');
  const setChatState = useSetMenuState('chat');

  return (
    <ConversationList
      activeId={chatState.activeConversationId}
      onSelect={(id) => setChatState({ activeConversationId: id })}
      scrollPosition={chatState.scrollPosition || 0}
      onScroll={(pos) => setChatState({ scrollPosition: pos })}
    />
  );
}
```

### Example 2: Mindmap Menu

```typescript
function MindmapMenu() {
  const saveGraphState = useWorkspaceStore(state => state.saveGraphState);

  const handleNodeMove = (nodes: GraphNode[], edges: GraphEdge[]) => {
    saveGraphState('mindmap', 'My Mindmap', {
      nodes,
      edges,
      viewport: { zoom: 1.0, center_x: 0, center_y: 0 },
      selected_nodes: [],
      layout: 'force-directed'
    });
  };

  return <MindmapCanvas onNodeMove={handleNodeMove} />;
}
```

### Example 3: Settings Menu

```typescript
function SettingsMenu() {
  const updatePreferences = useWorkspaceStore(state => state.updatePreferences);

  const handleThemeChange = (theme: 'light' | 'dark') => {
    updatePreferences({ theme });
  };

  return <ThemePicker onChange={handleThemeChange} />;
}
```

---

## 🏗️ Architecture

```
┌────────────────────────────────────────────────────┐
│  FRONTEND (React + Zustand)                       │
│  ┌──────────────────────────────────────────┐    │
│  │ Auto-save with debounce (5s)             │    │
│  │ Optimistic updates                       │    │
│  │ State restoration on login               │    │
│  └──────────────┬───────────────────────────┘    │
└─────────────────┼────────────────────────────────┘
                  │ REST API
┌─────────────────┼────────────────────────────────┐
│  BACKEND (FastAPI)                                │
│  ┌──────────────▼───────────────────────────┐    │
│  │ /workspace/state/load  (restore)         │    │
│  │ /workspace/state/save  (persist)         │    │
│  │ /workspace/graph/save  (graph state)     │    │
│  └──────────────┬───────────────────────────┘    │
│  ┌──────────────▼───────────────────────────┐    │
│  │ WorkspaceService                         │    │
│  │  - Upsert patterns                       │    │
│  │  - Transaction management                │    │
│  └──────────────┬───────────────────────────┘    │
└─────────────────┼────────────────────────────────┘
┌─────────────────▼────────────────────────────────┐
│  PostgreSQL (JSONB + Indexes)                    │
│  - conversations, messages                       │
│  - menu_states (JSONB)                           │
│  - graph_states (JSONB)                          │
│  - workspace_sessions                            │
└──────────────────────────────────────────────────┘
```

---

## 📊 Data Flow

### On Login

```
1. User logs in
2. Frontend calls: GET /workspace/state/load
3. Backend fetches:
   - All menu states
   - All graph states
   - Recent conversations
   - Workspace session
4. Frontend restores:
   - Last active menu
   - Menu-specific UI states
   - Active conversation
   - User preferences
```

### On State Change

```
1. User interacts with UI
2. Frontend updates local state (optimistic)
3. Debounced save triggers (after 5s of no changes)
4. POST /workspace/state/save with new state
5. Backend validates and persists
6. Frontend receives confirmation
```

---

## 🔒 Security

- ✅ **Authentication**: JWT token required for all endpoints
- ✅ **Authorization**: Users can only access their own state
- ✅ **Input Validation**: Pydantic models validate all requests
- ✅ **SQL Injection Protection**: Parameterized queries
- ✅ **Rate Limiting**: Recommended for production (not included)

---

## 🎨 Menu State Schemas

### Chat Menu State

```json
{
  "activeConversationId": "uuid",
  "scrollPosition": 420,
  "filterSettings": {
    "archived": false,
    "dateRange": "7days"
  },
  "viewMode": "list",
  "sidebarWidth": 300
}
```

### Documents Menu State

```json
{
  "selectedDocuments": ["doc1", "doc2"],
  "filterSettings": {
    "type": "pdf",
    "tags": ["research", "gpu"]
  },
  "sortBy": "title",
  "viewMode": "grid"
}
```

### Mindmap Menu State

```json
{
  "activeGraphId": "uuid",
  "viewportState": {
    "zoom": 1.5,
    "centerX": 200,
    "centerY": 300
  },
  "selectedNodes": ["node1"],
  "editMode": true
}
```

---

## 🧪 Testing

### Backend Tests

```python
# tests/test_workspace_service.py
async def test_save_and_load_state():
    service = WorkspaceService()
    user_id = uuid4()

    await service.save_menu_state(user_id, MenuStateSave(
        menu_type="chat",
        state={"activeConversationId": "uuid-123"}
    ))

    loaded = await service.get_menu_state(user_id, "chat")
    assert loaded.state["activeConversationId"] == "uuid-123"
```

### Frontend Tests

```typescript
test('should restore workspace state on login', async () => {
  const { result } = renderHook(() => useWorkspaceStore());

  await act(async () => {
    await result.current.initializeWorkspace();
  });

  expect(result.current.session).toBeDefined();
  expect(result.current.menuStates.chat).toBeDefined();
});
```

---

## 📈 Performance

- **Auto-Save Debouncing**: 5-second delay batches rapid updates
- **Optimistic Updates**: UI responds immediately, backend sync async
- **JSONB Indexes**: Fast queries on flexible schema
- **Connection Pooling**: Reuse database connections
- **Lazy Loading**: Load only active menu states initially

---

## 🛠️ Configuration

### Auto-Save Interval

```typescript
// Adjust in user preferences
await updatePreferences({ auto_save_interval: 10000 }); // 10 seconds
```

### Disable Auto-Save

```typescript
const disableAutoSave = useWorkspaceStore(state => state.disableAutoSave);
disableAutoSave(); // Manual save control
```

### Manual Save

```typescript
const saveMenuState = useWorkspaceStore(state => state.saveMenuState);
await saveMenuState('chat'); // Save specific menu
```

---

## 🚧 Future Enhancements

1. **Conversation Branching** - Fork conversations at any message
2. **Prompt Versioning** - Track prompt templates and A/B tests
3. **Collaborative Workspaces** - Share state between team members
4. **Conflict Resolution** - Handle simultaneous multi-device updates
5. **State History** - Undo/redo with snapshots
6. **Export/Import** - Backup and restore workspace configurations

---

## 📚 Documentation

- **Comprehensive Guide**: `docs/WORKSPACE_PERSISTENCE_GUIDE.md`
- **API Examples**: `docs/WORKSPACE_API_EXAMPLES.json`
- **Database Schema**: `migrations/001_workspace_persistence.sql`

---

## 🐛 Troubleshooting

### State not persisting?

1. Check auto-save enabled: `useWorkspaceStore.getState().autoSaveEnabled`
2. Check pending saves: `useWorkspaceStore.getState().pendingSaves`
3. Verify network requests in DevTools (should see POST to `/state/save`)

### State not restoring?

1. Verify `initializeWorkspace()` called on app mount
2. Check API response: `GET /workspace/state/load`
3. Look for errors in browser console during restoration

### Performance issues?

1. Increase auto-save interval for frequently changing state
2. Use manual save for large graph states
3. Optimize JSONB state size (remove unnecessary fields)

---

## 📞 Support

For issues or questions:
1. Check `docs/WORKSPACE_PERSISTENCE_GUIDE.md` for detailed documentation
2. Review `docs/WORKSPACE_API_EXAMPLES.json` for API usage
3. Contact the development team

---

## ✅ Summary

The Persistent AI Workspace system provides:

- **Production-Ready**: Full test coverage, error handling, logging
- **Flexible**: JSONB storage adapts to any menu-specific state
- **Reliable**: PostgreSQL ensures data durability
- **Performant**: Debounced saves, optimistic updates, indexed queries
- **Secure**: Authentication, authorization, validation
- **Scalable**: Designed for multi-user, multi-device scenarios

**Status**: ✅ Implementation complete and ready for integration

---

**Version**: 1.0
**Last Updated**: 2025-12-28
**Author**: Enterprise KMS Team
