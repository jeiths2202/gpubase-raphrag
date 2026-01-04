"""
Attachment Entity - Represents file attachments linked to IMS issues
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional, Dict, Any
from uuid import UUID, uuid4


class AttachmentType(str, Enum):
    """Attachment type enumeration"""
    PDF = "pdf"
    WORD = "word"
    EXCEL = "excel"
    IMAGE = "image"
    TEXT = "text"
    OTHER = "other"


@dataclass
class Attachment:
    """
    Attachment entity representing a file attached to an IMS issue.

    Supports document processing (PDF, Word), OCR for images,
    and text extraction for semantic search.
    """

    # Identity
    id: UUID = field(default_factory=uuid4)
    issue_id: UUID = field(default_factory=uuid4)  # Parent issue reference

    # File Attributes
    filename: str = ""
    original_url: str = ""
    file_size: int = 0  # bytes
    mime_type: str = "application/octet-stream"
    attachment_type: AttachmentType = AttachmentType.OTHER

    # Content
    extracted_text: str = ""  # Text extracted via PyPDF2, pdfplumber, OCR
    text_length: int = 0

    # Metadata
    uploaded_by: str = ""
    uploaded_at: datetime = field(default_factory=datetime.utcnow)

    # Processing Status
    is_processed: bool = False
    processed_at: Optional[datetime] = None
    processing_error: Optional[str] = None

    # Storage
    storage_path: Optional[str] = None  # Local file path or S3 key

    def __post_init__(self):
        """Validate entity invariants"""
        if not self.filename:
            raise ValueError("Attachment must have a filename")

        # Auto-detect attachment type from filename
        if not self.attachment_type or self.attachment_type == AttachmentType.OTHER:
            self.attachment_type = self._detect_type_from_filename()

    def _detect_type_from_filename(self) -> AttachmentType:
        """Detect attachment type from filename extension"""
        ext = self.filename.lower().split('.')[-1] if '.' in self.filename else ''

        type_mapping = {
            'pdf': AttachmentType.PDF,
            'doc': AttachmentType.WORD,
            'docx': AttachmentType.WORD,
            'xls': AttachmentType.EXCEL,
            'xlsx': AttachmentType.EXCEL,
            'png': AttachmentType.IMAGE,
            'jpg': AttachmentType.IMAGE,
            'jpeg': AttachmentType.IMAGE,
            'gif': AttachmentType.IMAGE,
            'txt': AttachmentType.TEXT,
            'md': AttachmentType.TEXT,
        }

        return type_mapping.get(ext, AttachmentType.OTHER)

    def mark_as_processed(self, extracted_text: str) -> None:
        """Mark attachment as successfully processed"""
        self.extracted_text = extracted_text
        self.text_length = len(extracted_text)
        self.is_processed = True
        self.processed_at = datetime.utcnow()
        self.processing_error = None

    def mark_as_failed(self, error: str) -> None:
        """Mark attachment processing as failed"""
        self.is_processed = False
        self.processing_error = error
        self.processed_at = datetime.utcnow()

    def is_searchable(self) -> bool:
        """Check if attachment has searchable text content"""
        return self.is_processed and len(self.extracted_text) > 0

    def to_dict(self) -> Dict[str, Any]:
        """Convert entity to dictionary for persistence"""
        return {
            "id": str(self.id),
            "issue_id": str(self.issue_id),
            "filename": self.filename,
            "original_url": self.original_url,
            "file_size": self.file_size,
            "mime_type": self.mime_type,
            "attachment_type": self.attachment_type.value,
            "extracted_text": self.extracted_text,
            "text_length": self.text_length,
            "uploaded_by": self.uploaded_by,
            "uploaded_at": self.uploaded_at.isoformat(),
            "is_processed": self.is_processed,
            "processed_at": self.processed_at.isoformat() if self.processed_at else None,
            "processing_error": self.processing_error,
            "storage_path": self.storage_path,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Attachment":
        """Create entity from dictionary"""
        return cls(
            id=UUID(data["id"]) if isinstance(data.get("id"), str) else data.get("id", uuid4()),
            issue_id=UUID(data["issue_id"]) if isinstance(data.get("issue_id"), str) else data.get("issue_id", uuid4()),
            filename=data["filename"],
            original_url=data.get("original_url", ""),
            file_size=data.get("file_size", 0),
            mime_type=data.get("mime_type", "application/octet-stream"),
            attachment_type=AttachmentType(data.get("attachment_type", "other")),
            extracted_text=data.get("extracted_text", ""),
            text_length=data.get("text_length", 0),
            uploaded_by=data.get("uploaded_by", ""),
            uploaded_at=datetime.fromisoformat(data["uploaded_at"]) if isinstance(data.get("uploaded_at"), str) else data.get("uploaded_at", datetime.utcnow()),
            is_processed=data.get("is_processed", False),
            processed_at=datetime.fromisoformat(data["processed_at"]) if data.get("processed_at") else None,
            processing_error=data.get("processing_error"),
            storage_path=data.get("storage_path"),
        )
