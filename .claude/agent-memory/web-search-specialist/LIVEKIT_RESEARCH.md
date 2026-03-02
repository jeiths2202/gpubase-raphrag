# LiveKit Research: Remote Expert Screen Sharing Implementation

## Project Context
Research for KMS (Knowledge Management System) premium support feature - users click "Premium Support" to share screen with remote expert.

## 1. LiveKit Architecture Overview

### Core Concept
LiveKit is an **open-source WebRTC Selective Forwarding Unit (SFU)** - a specialized media router optimized for low-latency, high-bandwidth forwarding without transcoding individual packets.

### Key Features
- **Real-time communication**: Enables peer-to-peer or server-routed WebRTC
- **Cross-platform**: Works on web, mobile, backend services, telephony
- **Horizontally scalable**: Run on 1 or 100+ nodes with identical config
- **AI-first architecture**: AI agents join rooms as full WebRTC participants

### Technical Foundation
- **Language**: Written in Go
- **WebRTC stack**: Uses Pion's Go-based WebRTC implementation
- **Media**: SFU forwards media streams without transcoding (preserves quality)
- **Signaling**: Low-latency signaling over WebSocket/HTTP

---

## 2. How LiveKit Works: 5-Layer Architecture

```
Layer 5: External Clients & Services
├── Web/Mobile WebRTC clients
├── Backend services
└── External workers (agents)

Layer 4: Entry Layer (Entry Points)
├── HTTP endpoints
├── WebSocket protocol
└── API endpoints

Layer 3: Core Session Management
├── Room lifecycle orchestration
└── Participant management

Layer 2: Media Forwarding (SFU)
├── RTP routing
├── Adaptive degradation
└── Quality-of-Service (QoS)

Layer 1: Infrastructure Services
├── State storage (Redis)
├── Routing/messaging
└── Telemetry
```

### Key Concept: Rooms, Participants, Tracks
- **Room**: Virtual space where participants connect
- **Participant**: User/agent in a room
- **Track**: Individual media stream (video, audio, screen)

### Publishing/Subscribing Pattern
1. User A publishes camera → becomes a video track
2. User B publishes screen → becomes a screen_share track
3. Both users subscribe to each other's tracks
4. SFU receives all tracks, forwards to each subscriber

---

## 3. LiveKit Components for Screen Sharing

### Client-Side SDKs
| Platform | Package | Key Classes |
|----------|---------|------------|
| **JavaScript/Web** | `livekit-client` | `LocalParticipant`, `Room`, `LocalScreencastVideoTrack` |
| **React** | `@livekit/components-react` | `VideoConference`, `VideoTrack`, `LiveKitRoom` |
| **React Native** | `livekit-react-native` | Similar to web SDK |
| **Python (backend)** | `livekit-agents` | `AgentDispatcher`, `RoomService` |

### Core React Components
```
@livekit/components-react provides:
├── <LiveKitRoom /> - Root component for room connection
├── <VideoConference /> - Drop-in conferencing UI
│   └── Includes screen sharing button
├── <Participant /> - Single participant video display
├── <VideoTrack /> - Renders video/screen tracks
├── <ControlBar /> - Audio/video/screen sharing controls
├── <GridLayout /> - Multi-participant grid view
├── <FocusLayout /> - Single focused participant
└── <Chat /> - Non-persistent messaging
```

### Backend Components
| Component | Role |
|-----------|------|
| **LiveKit Server** | Media SFU + signaling server |
| **RoomService API** | REST API for room management |
| **Webhook System** | Event notifications (participant join/leave) |
| **Egress Service** | Recording/streaming (optional) |

---

## 4. Screen Sharing Implementation Details

### How Screen Sharing Works in LiveKit

#### Track Types
```
Participant tracks:
├── camera (video)
├── microphone (audio)
├── screen_share (video - from screen capture)
└── screen_share_audio (audio - browser tab audio)
```

#### Publishing Screen Capture
```
Browser API (getUserDisplayMedia)
    ↓
LocalParticipant.setScreenShareEnabled(true)
    ↓
LiveKit publishes as video track with kind="screen_share"
    ↓
Server forwards to all room participants
    ↓
Subscribers render with <VideoTrack kind="screen_share" />
```

### React Implementation

#### Option 1: Using VideoConference Component (Easiest)
```typescript
import { VideoConference } from '@livekit/components-react';
import { getRoomToken } from './api';

export function PremiumSupport() {
  const [token, setToken] = useState<string>();

  useEffect(() => {
    getRoomToken('expert-room', 'customer-123').then(setToken);
  }, []);

  if (!token) return <div>Loading...</div>;

  return (
    <VideoConference
      token={token}
      serverUrl="wss://your-livekit-server.com"
      roomName="expert-room"
    />
  );
}
```
- Pre-built UI with screen sharing button
- No state management needed
- Handles track subscription automatically

#### Option 2: Custom Implementation
```typescript
import { LocalParticipant } from '@livekit/components-react';
import { useLocalParticipant } from '@livekit/components-react';

export function CustomScreen() {
  const { localParticipant } = useLocalParticipant();

  const toggleScreenShare = async () => {
    await localParticipant?.setScreenShareEnabled(true);
    // Browser prompts user to select screen
  };

  return <button onClick={toggleScreenShare}>Share Screen</button>;
}
```

#### Screen Share Display (Both Options)
```typescript
import { VideoTrack, Participant } from '@livekit/components-react';

// Renders all participant tracks including screen_share
{participant.videoTracks.map((track) => (
  <VideoTrack key={track.sid} track={track.videoTrack!} />
))}
```

### Key Implementation Details
1. **Browser Prompt**: `setScreenShareEnabled(true)` triggers native browser dialog
2. **Tab Audio**: User must select "Share tab audio" for screen audio
3. **Dual Tracks**: One participant can publish camera + screen simultaneously
4. **Track Source**: Screen published as video track (not separate type)
5. **No Transcoding**: Screen content stays in original resolution/codec

---

## 5. Authentication: JWT Tokens & Room Access

### Token-Based Authentication Flow

```
┌──────────────────┐
│   React Client   │
└────────┬─────────┘
         │ 1. User clicks "Premium Support"
         ↓
┌──────────────────┐
│   Backend API    │ ← Generate JWT token
│ /api/room-token  │
└────────┬─────────┘
         │ 2. POST /api/room-token (room="expert-1", participant="user-123")
         ↓ 3. Returns JWT token + server URL
┌──────────────────┐
│  React Client    │
│  (token received)│ ← Store token securely
└────────┬─────────┘
         │ 4. Connect with LiveKitRoom(token, serverUrl)
         ↓
┌──────────────────────────┐
│  LiveKit Server (SFU)     │
│  Validate JWT token      │
└────────┬─────────────────┘
         │ 5. Room joined successfully
         ↓
    [Participant connected]
```

### Token Structure (JWT)

```json
{
  "iss": "livekit",
  "sub": "expert-room",  // room name
  "iat": 1234567890,
  "exp": 1234571490,
  "grants": {
    "identity": "user-123",
    "name": "John Doe",
    "video": {
      "canPublish": true,        // Can publish camera
      "canPublishData": true,    // Can send data messages
      "canSubscribe": true,      // Can receive others' tracks
      "ingressAdmin": false,
      "roomJoin": true,
      "roomList": false
    }
  }
}
```

### Backend Token Generation

#### Python Example
```python
from livekit import api

# Configuration
LIVEKIT_URL = "http://localhost:7880"
LIVEKIT_API_KEY = "your-api-key"
LIVEKIT_API_SECRET = "your-api-secret"

async def get_room_token(room_name: str, participant_name: str):
    """Generate JWT token for client"""
    token = api.AccessToken(LIVEKIT_API_KEY, LIVEKIT_API_SECRET)

    # Set grants
    token.identity = participant_name
    token.name = participant_name
    grant = token.grants
    grant.can_publish = True
    grant.can_subscribe = True
    grant.room_join = True
    grant.room = room_name

    # Token expires in 10 minutes
    token.ttl = 600

    return await token.to_jwt()
```

#### Node.js Example
```javascript
const { AccessToken } = require('livekit-server-sdk');

async function getRoomToken(roomName, participantName) {
  const at = new AccessToken('your-api-key', 'your-api-secret');

  at.identity = participantName;
  at.name = participantName;
  at.grants = {
    canPublish: true,
    canSubscribe: true,
    roomJoin: true,
    room: roomName
  };

  return at.toJwt();
}
```

#### FastAPI Integration Example
```python
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from app.api.core.config import settings

router = APIRouter(prefix="/api", tags=["room"])

class RoomTokenRequest(BaseModel):
    room_name: str
    participant_name: str

@router.post("/room-token")
async def generate_room_token(
    req: RoomTokenRequest,
    current_user = Depends(get_current_user)
):
    """Generate JWT token for LiveKit room"""
    token = api.AccessToken(
        settings.livekit_api_key,
        settings.livekit_api_secret
    )

    token.identity = current_user.get("user_id")
    token.name = current_user.get("username")
    token.grants.can_publish = True
    token.grants.can_subscribe = True
    token.grants.room = req.room_name
    token.ttl = 600  # 10 minutes

    return {
        "token": await token.to_jwt(),
        "server_url": settings.livekit_server_url
    }
```

### Token Permissions Breakdown

| Grant | Effect | Use Case |
|-------|--------|----------|
| `canPublish: true` | Can publish camera/microphone/screen | Expert shares screen |
| `canPublish: false` | Cannot publish own media | View-only participant |
| `canSubscribe: true` | Can receive others' tracks | Must be true for screen view |
| `canPublishData: true` | Can send messages/data | Chat functionality |
| `roomJoin: true` | Can join the room | Required |

### Token Lifecycle
- **Expiration**: Set short TTL (10 minutes recommended)
- **Refresh**: Server can issue refreshed tokens for reconnection
- **Revocation**: On Cloud only; self-hosted requires token expiration
- **Short TTL Benefit**: Prevents replay attacks, old permissions can't be reused

---

## 6. Deployment Options

### Option A: LiveKit Cloud (Managed)

#### Pricing Plans
| Plan | Monthly | Participants | Min/Month | Bandwidth |
|------|---------|-------------|-----------|-----------|
| **Build** | $0 | 100 | 5,000 min | 50 GB |
| **Ship** | $50 | 1,000 | 150,000 min | 250 GB |
| **Scale** | $500 | Unlimited | 1.5M min | 3 TB |

#### Advantages
- ✅ Zero infrastructure management
- ✅ Global CDN for low-latency media
- ✅ Enterprise SLA support available
- ✅ Built-in observability dashboards
- ✅ Fully managed agent deployments

#### Setup
- Sign up at https://livekit.io/cloud
- Create API key/secret
- Use same SDKs as self-hosted (no code changes)

---

### Option B: Self-Hosted Docker

#### Single Node (Development)
```bash
# Quick start with docker-compose
docker run --rm \
  -e LIVEKIT_API_KEY=your-key \
  -e LIVEKIT_API_SECRET=your-secret \
  -p 7880:7880 \
  -p 7881:7881 \
  -p 7882:7882 \
  livekit/livekit-server:latest
```

#### Production Deployment (Cloud-Init + Docker Compose)

**Requirements:**
- Domain + SSL certificate
- 10Gbps ethernet (recommended)
- Load balancer for HTTPS/SSL termination
- Public IP with UDP port access (7880-7882)

**Architecture:**
```
┌─────────────────┐
│  Load Balancer  │ (HTTPS/SSL termination)
└────────┬────────┘
         │
┌────────┴────────────────────┐
│  LiveKit Server (SFU)        │
│  - Docker container          │
│  - Host networking enabled   │
│  - Caddy reverse proxy       │
└─────────────────────────────┘
```

**Configuration (docker-compose):**
```yaml
version: '3.8'
services:
  livekit:
    image: livekit/livekit-server:latest
    environment:
      LIVEKIT_API_KEY: your-key
      LIVEKIT_API_SECRET: your-secret
      LIVEKIT_BIND_ADDRESSES: 0.0.0.0
      LIVEKIT_USE_EXTERNAL_IP: "true"
      LIVEKIT_PUBLIC_IP: your-public-ip
    ports:
      - "7880:7880"      # WebRTC
      - "7881:7881"      # HTTP
      - "7882:7882/udp"  # TURN
    network_mode: host   # Critical for performance
```

#### Multi-Node (Distributed)

**Requirements:**
- Redis instance for state coordination
- Multiple LiveKit server instances
- Load balancer with sticky sessions
- Kubernetes (recommended)

**Architecture:**
```
┌─────────────────────────────────────┐
│         Load Balancer               │
│     (sticky sessions)               │
└────────────┬────────────────────────┘
             │
    ┌────────┼────────┐
    ↓        ↓        ↓
┌──────┐ ┌──────┐ ┌──────┐
│Node 1│ │Node 2│ │Node 3│  (LiveKit SFU instances)
└──┬───┘ └──┬───┘ └──┬───┘
   │        │        │
   └────────┼────────┘
            ↓
        ┌────────┐
        │ Redis  │  (State coordination)
        └────────┘
```

**Key Constraints:**
- Each room stays on ONE node (not distributed)
- Media (RTP) stays local to node
- Only signaling through Redis
- Participants join same room → connect to same node

---

### Option C: Kubernetes Deployment

**Recommended for production:**

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: livekit-server
spec:
  replicas: 3
  template:
    spec:
      containers:
      - name: livekit
        image: livekit/livekit-server:latest
        env:
        - name: LIVEKIT_REDIS_URL
          value: redis://redis-service:6379
        ports:
        - containerPort: 7880  # WebRTC
        - containerPort: 7881  # HTTP
        - containerPort: 7882  # UDP TURN
        resources:
          requests:
            cpu: 2
            memory: 4Gi
          limits:
            cpu: 4
            memory: 8Gi
```

---

## 7. System Requirements

### LiveKit Server
| Component | Requirement | Notes |
|-----------|-------------|-------|
| **CPU** | 2-4 cores minimum | Compute-optimized instances recommended |
| **Memory** | 4-8 GB | Scales with concurrent participants |
| **Network** | 10Gbps ethernet | For production |
| **Bandwidth** | ~1.5 Mbps per participant | Depends on resolution/codec |
| **UDP Ports** | 7880-7882, TURN | Required for media |

### Recommended VM Specs (AWS Example)
```
Single-node (dev): t3.large (2 vCPU, 8 GB RAM)
Single-node (prod): c5.2xlarge (8 vCPU, 16 GB RAM, EBS-optimized)
Multi-node (prod): c5.4xlarge per node
```

### Agent Server (for AI agents)
- **CPU**: 4 cores minimum
- **Memory**: 8 GB minimum
- **Per Job**: Can handle 10-25 concurrent jobs

### Egress Service (Recording/Streaming)
- **CPU**: 4 cores
- **Memory**: 4 GB
- **Video Processing**: 2-6 cores with transcoding

### Container Requirements
- **Host networking**: MUST be enabled for optimal performance
- **UDP access**: Firewall must allow UDP ports
- **Public IP**: Server needs public IP for external clients

---

## 8. Pricing Comparison: Cloud vs Self-Hosted

### LiveKit Cloud
```
Scenario: 20 concurrent video calls, 5 min average
Monthly usage: 20 × 5 min × 30 days = 3,000 min
Monthly cost: $0 (within Build plan free tier)

Scenario: 100 concurrent video calls, 30 min average
Monthly usage: 100 × 30 × 30 = 90,000 min
Monthly cost: $50 (Ship plan includes 150K min)
```

### Self-Hosted
```
Infrastructure costs (AWS c5.2xlarge):
- Compute: ~$300/month
- Data transfer: ~$100/month (assuming 1TB egress)
- Storage: ~$50/month
Total: ~$450/month + DevOps labor

Scale with multiple nodes:
- 3× c5.2xlarge: ~$900/month
- Redis + Load Balancer: ~$200/month
- Total: ~$1,100/month

Break-even: 1,000+ concurrent participants
```

### Decision Matrix
| Factor | Cloud | Self-Hosted |
|--------|-------|-------------|
| **Setup Time** | Minutes | Days |
| **Upfront Cost** | $0 | $500-1000 |
| **Monthly Cost** | Pay-as-you-go | Fixed infrastructure |
| **Data Privacy** | Managed by LiveKit | Your control |
| **Support** | Enterprise available | Community Slack |
| **Customization** | Limited | Full control |

---

## 9. Implementation Roadmap for KMS Premium Support

### Phase 1: Setup (Week 1)
- [ ] Choose deployment: Cloud (easiest) or Self-hosted Docker
- [ ] Create LiveKit account / deploy server
- [ ] Get API key + secret
- [ ] Install `livekit-client` + `@livekit/components-react`

### Phase 2: Backend Integration (Week 1-2)
- [ ] Create `/api/room-token` endpoint (FastAPI)
- [ ] Generate JWT tokens with room + participant info
- [ ] Add authentication check (only premium users)
- [ ] Return token + server URL to frontend

### Phase 3: Frontend UI (Week 2)
- [ ] Create `PremiumSupportPage` component
- [ ] Import `VideoConference` from `@livekit/components-react`
- [ ] Connect to LiveKit with token
- [ ] Test screen sharing button

### Phase 4: Testing (Week 2-3)
- [ ] Test 1-on-1 expert sessions
- [ ] Verify screen sharing quality
- [ ] Test reconnection after disconnect
- [ ] Load test with multiple rooms

### Phase 5: Production (Week 3)
- [ ] Deploy to production (Cloud or self-hosted)
- [ ] Monitor performance with observability dashboard
- [ ] Set up webhook for room events (optional)
- [ ] Add recording feature (egress service)

---

## Key Files to Review
- [LiveKit Documentation](https://docs.livekit.io/)
- [React Components Reference](https://docs.livekit.io/reference/components/react/)
- [Screen Sharing Guide](https://docs.livekit.io/transport/media/screenshare/)
- [Token Generation](https://docs.livekit.io/home/server/generating-tokens/)
- [Self-Hosting Guide](https://docs.livekit.io/transport/self-hosting/)

---

## Notes for KMS Project Integration

1. **Architecture**: LiveKit is SFU (Selective Forwarding) - not MCU, so low CPU overhead
2. **Scalability**: Can handle 100s of concurrent rooms on single node
3. **No Transcoding**: Screen content stays in original codec (important for clarity)
4. **Security**: JWT tokens with 10-min TTL prevent unauthorized access
5. **Minimal Backend**: Only need token generation endpoint
6. **React Integration**: Use `@livekit/components-react` for quick implementation
7. **Cost Prediction**: Cloud likely best for initial deployment (no infrastructure)
8. **Monitoring**: Both Cloud and self-hosted have observability dashboards

---

Generated: 2026-02-25
Search Sources: Official LiveKit documentation, GitHub repositories, architecture guides
