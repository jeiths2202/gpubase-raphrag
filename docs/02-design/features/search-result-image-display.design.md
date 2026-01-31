# Design: 검색 결과 이미지/표 출력 기능

## 1. 아키텍처 개요

```
┌─────────────────────────────────────────────────────────────────────────┐
│                           Frontend (React)                               │
│  ┌──────────────────────────────────────────────────────────────────┐   │
│  │ OpenAgentPage / OpenFrameRAGPage                                  │   │
│  │  ├─ useStreamingChat Hook                                         │   │
│  │  │    └─ Handle chunk_type: "images"                              │   │
│  │  └─ ImageGallery Component                                        │   │
│  │       └─ Render base64 images inline                              │   │
│  └──────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────┘
                                     ▲
                                     │ SSE Stream
                                     │ {chunk_type: "images", images: [...]}
                                     │
┌─────────────────────────────────────────────────────────────────────────┐
│                           Backend (FastAPI)                              │
│  ┌──────────────────────────────────────────────────────────────────┐   │
│  │ AgentOrchestrator.stream()                                        │   │
│  │  ├─ yield text chunks                                             │   │
│  │  ├─ yield sources chunk                                           │   │
│  │  └─ yield images chunk (NEW)                                      │   │
│  └──────────────────────────────────────────────────────────────────┘   │
│                                     ▲                                    │
│                                     │                                    │
│  ┌──────────────────────────────────────────────────────────────────┐   │
│  │ AgentExecutor.execute()                                           │   │
│  │  ├─ Execute RAG agent                                             │   │
│  │  ├─ Collect sources                                               │   │
│  │  └─ Call FigureImageService.get_images_for_sources() (NEW)        │   │
│  └──────────────────────────────────────────────────────────────────┘   │
│                                     ▲                                    │
│                                     │                                    │
│  ┌──────────────────────────────────────────────────────────────────┐   │
│  │ FigureImageService (existing)                                     │   │
│  │  └─ get_images_for_sources(sources) → List[ImageData]            │   │
│  └──────────────────────────────────────────────────────────────────┘   │
│                                     ▲                                    │
│                                     │                                    │
│  ┌──────────────────────────────────────────────────────────────────┐   │
│  │ PostgresImageEmbeddingRepository                                  │   │
│  │  └─ SELECT image_data FROM image_embeddings WHERE ...             │   │
│  └──────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────┘
```

## 2. 데이터 모델

### 2.1 백엔드 - 이미지 응답 스키마

```python
# app/api/agents/types.py

class ImageData(BaseModel):
    """이미지 데이터 for frontend display"""
    id: str
    document_id: str
    page_number: int
    figure_reference: Optional[str] = None
    figure_caption: Optional[str] = None
    description: Optional[str] = None
    width: Optional[int] = None
    height: Optional[int] = None
    mime_type: str = "image/png"
    data: Optional[str] = None  # base64 data URL

class StreamingChunk(BaseModel):
    chunk_type: Literal["text", "sources", "images", "metadata", "error", "done"]
    content: Optional[str] = None
    sources: Optional[List[SourceInfo]] = None
    images: Optional[List[ImageData]] = None  # NEW
    metadata: Optional[Dict[str, Any]] = None
```

### 2.2 프론트엔드 - 타입 정의

```typescript
// kms-portal-ui/src/pages/OpenAgentPage.tsx

interface ImageData {
  id: string;
  document_id: string;
  page_number: number;
  figure_reference?: string;
  figure_caption?: string;
  description?: string;
  width?: number;
  height?: number;
  mime_type: string;
  data?: string;  // base64 data URL e.g. "data:image/png;base64,..."
}

interface Message {
  // ... existing fields
  images?: ImageData[];  // Changed from ImageContent[]
}
```

## 3. 컴포넌트 설계

### 3.1 Backend - AgentExecutor 수정

**파일**: `app/api/agents/executor.py`

```python
async def _execute_with_images(
    self,
    request: AgentRequest,
    agent: BaseAgent,
    context: AgentContext
) -> Tuple[AgentResult, List[ImageData]]:
    """Execute agent and fetch related images"""

    # 1. Execute agent
    result = await agent.execute(request.task, context)

    # 2. Get images if sources available
    images = []
    if result.sources:
        try:
            figure_service = await self._get_figure_image_service()
            images = await figure_service.get_images_for_sources(
                sources=result.sources,
                include_data=True
            )
        except Exception as e:
            logger.warning(f"Failed to fetch images: {e}")

    return result, images
```

### 3.2 Backend - Orchestrator 스트리밍 수정

**파일**: `app/api/agents/orchestrator.py`

```python
async def stream(
    self,
    request: AgentRequest,
    user_id: Optional[str] = None
) -> AsyncGenerator[StreamingChunk, None]:
    """Stream agent execution with images"""

    # ... existing text and sources streaming

    # After sources, yield images
    if images:
        yield StreamingChunk(
            chunk_type="images",
            images=images
        )

    yield StreamingChunk(chunk_type="done")
```

### 3.3 Frontend - ImageGallery 컴포넌트

**파일**: `kms-portal-ui/src/components/ImageGallery.tsx`

```tsx
interface ImageGalleryProps {
  images: ImageData[];
  onImageClick?: (image: ImageData) => void;
}

export const ImageGallery: React.FC<ImageGalleryProps> = ({ images, onImageClick }) => {
  const [selectedImage, setSelectedImage] = useState<ImageData | null>(null);

  if (!images || images.length === 0) return null;

  return (
    <div className="image-gallery">
      <div className="gallery-header">
        <span>관련 이미지/표 ({images.length})</span>
      </div>
      <div className="gallery-grid">
        {images.map((img) => (
          <div key={img.id} className="gallery-item" onClick={() => setSelectedImage(img)}>
            <img
              src={img.data}
              alt={img.figure_caption || img.figure_reference || 'Image'}
              loading="lazy"
            />
            {img.figure_caption && (
              <div className="image-caption">{img.figure_caption}</div>
            )}
          </div>
        ))}
      </div>

      {/* Image Modal */}
      {selectedImage && (
        <ImageModal
          image={selectedImage}
          onClose={() => setSelectedImage(null)}
        />
      )}
    </div>
  );
};
```

### 3.4 Frontend - useStreamingChat 수정

**파일**: `kms-portal-ui/src/components/AgentChat/hooks/useStreamingChat.ts`

```typescript
// Handle images chunk
else if (chunk.chunk_type === 'images') {
  const imageData = (chunk.images || []).map((img: any) => ({
    id: img.id,
    document_id: img.document_id,
    page_number: img.page_number,
    figure_reference: img.figure_reference,
    figure_caption: img.figure_caption,
    data: img.data,
    width: img.width,
    height: img.height,
    mime_type: img.mime_type
  }));

  // Store images to attach to message
  pendingImages = imageData;
}
```

## 4. API 흐름

### 4.1 SSE 스트림 이벤트 순서

```
1. data: {"chunk_type": "metadata", "metadata": {"agent_type": "rag"}}
2. data: {"chunk_type": "text", "content": "マッピング..."}
3. data: {"chunk_type": "text", "content": "・サポート..."}
   ... (more text chunks)
4. data: {"chunk_type": "sources", "sources": [...]}
5. data: {"chunk_type": "images", "images": [        // NEW
     {
       "id": "img_001",
       "figure_reference": "fig_1_1",
       "figure_caption": "マッピング・サポートの基本構造",
       "data": "data:image/png;base64,iVBORw0KGgo...",
       "page_number": 15,
       "width": 800,
       "height": 600
     }
   ]}
6. data: {"chunk_type": "done"}
```

## 5. 성능 최적화

### 5.1 이미지 크기 제한

```python
# figure_image_service.py

MAX_IMAGE_SIZE_KB = 500  # 500KB per image
MAX_IMAGES_PER_RESPONSE = 5

def _format_image_for_frontend(self, entity, include_data=True):
    # ... existing code

    if include_data and entity.image_data:
        # Check size limit
        if len(entity.image_data) > MAX_IMAGE_SIZE_KB * 1024:
            # Resize or skip large images
            logger.warning(f"Image {entity.image_id} exceeds size limit, skipping")
            return None

        b64_data = base64.b64encode(entity.image_data).decode('utf-8')
        result["data"] = f"data:{entity.mime_type};base64,{b64_data}"
```

### 5.2 Lazy Loading

```tsx
// Frontend - ImageGallery
<img
  src={img.data}
  loading="lazy"  // Native lazy loading
  decoding="async"  // Async decoding
/>
```

## 6. 에러 처리

### 6.1 이미지 로드 실패

```tsx
// Frontend
<img
  src={img.data}
  onError={(e) => {
    e.currentTarget.src = '/placeholder-image.svg';
    e.currentTarget.alt = 'Image load failed';
  }}
/>
```

### 6.2 백엔드 에러 처리

```python
# executor.py
try:
    images = await figure_service.get_images_for_sources(...)
except Exception as e:
    logger.error(f"Image fetch failed: {e}")
    images = []  # Continue without images
```

## 7. 구현 순서

1. **Step 1**: `types.py`에 `ImageData` 스키마 추가
2. **Step 2**: `figure_image_service.py`에 크기 제한 로직 추가
3. **Step 3**: `executor.py`에 이미지 조회 로직 추가
4. **Step 4**: `orchestrator.py`에 images 청크 스트리밍 추가
5. **Step 5**: Frontend `ImageGallery` 컴포넌트 생성
6. **Step 6**: `useStreamingChat.ts`에 images 청크 처리 추가
7. **Step 7**: `OpenAgentPage.tsx`에 ImageGallery 통합
8. **Step 8**: CSS 스타일링
9. **Step 9**: E2E 테스트

## 8. 테스트 케이스

| 테스트 | 기대 결과 |
|--------|----------|
| 이미지가 있는 쿼리 | 이미지 갤러리 표시 |
| 이미지가 없는 쿼리 | 갤러리 섹션 미표시 |
| 대용량 이미지 | 스킵 또는 리사이즈 |
| 이미지 클릭 | 모달 확대 보기 |
| 네트워크 오류 | 플레이스홀더 이미지 |
