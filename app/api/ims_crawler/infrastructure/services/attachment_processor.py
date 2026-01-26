"""
Attachment Processor Service - Text extraction from various file types

Extracts searchable text content from PDF, DOCX, images, and other attachments.
"""

import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


class AttachmentProcessor:
    """
    Processes attachments and extracts text content.

    Supports: PDF, DOCX, TXT, images (with OCR if available).
    """

    def __init__(self):
        """Initialize attachment processor."""
        pass

    def extract_text(self, filepath: Path) -> Optional[str]:
        """
        Extract text content from file.

        Args:
            filepath: Path to attachment file

        Returns:
            Extracted text or None if extraction fails
        """
        if not filepath.exists():
            logger.warning(f"File not found: {filepath}")
            return None

        suffix = filepath.suffix.lower()

        try:
            if suffix in ['.txt', '.log', '.md']:
                return self._extract_from_text(filepath)
            elif suffix == '.pdf':
                return self._extract_from_pdf(filepath)
            elif suffix in ['.doc', '.docx']:
                return self._extract_from_docx(filepath)
            elif suffix in ['.png', '.jpg', '.jpeg', '.bmp', '.gif']:
                return self._extract_from_image(filepath)
            else:
                logger.debug(f"No text extraction available for {suffix} files")
                return None

        except Exception as e:
            logger.error(f"Text extraction failed for {filepath}: {e}")
            return None

    @staticmethod
    def _extract_from_text(filepath: Path) -> str:
        """
        Extract text from plain text file.

        Args:
            filepath: Path to text file

        Returns:
            File contents as string
        """
        try:
            with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
                return f.read()
        except Exception as e:
            logger.warning(f"Failed to read text file {filepath}: {e}")
            return ""

    @staticmethod
    def _extract_from_pdf(filepath: Path) -> str:
        """
        Extract text from PDF file.

        Uses pdfplumber (preferred) with PyPDF2 as fallback.

        Args:
            filepath: Path to PDF file

        Returns:
            Extracted text from all pages
        """
        text_parts = []

        # Try pdfplumber first (better for complex PDFs)
        try:
            import pdfplumber

            with pdfplumber.open(filepath) as pdf:
                for page in pdf.pages:
                    text = page.extract_text()
                    if text:
                        text_parts.append(text)

            if text_parts:
                return '\n\n'.join(text_parts)

        except ImportError:
            logger.debug("pdfplumber not installed, trying PyPDF2")
        except Exception as e:
            logger.warning(f"pdfplumber failed for {filepath}: {e}")

        # Fallback to PyPDF2
        try:
            import PyPDF2

            with open(filepath, 'rb') as f:
                reader = PyPDF2.PdfReader(f)
                for page in reader.pages:
                    text = page.extract_text()
                    if text:
                        text_parts.append(text)

            return '\n\n'.join(text_parts)

        except ImportError:
            logger.error("Neither pdfplumber nor PyPDF2 installed")
            return ""
        except Exception as e:
            logger.error(f"PyPDF2 also failed for {filepath}: {e}")
            return ""

    @staticmethod
    def _extract_from_docx(filepath: Path) -> str:
        """
        Extract text from Word document (.docx).

        Args:
            filepath: Path to DOCX file

        Returns:
            Extracted text from all paragraphs
        """
        try:
            from docx import Document

            doc = Document(filepath)
            paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]
            return '\n\n'.join(paragraphs)

        except ImportError:
            logger.error("python-docx not installed")
            return ""
        except Exception as e:
            logger.error(f"Failed to extract from DOCX {filepath}: {e}")
            return ""

    @staticmethod
    def _extract_from_image(filepath: Path) -> str:
        """
        Extract text from image using OCR (if available).

        Requires pytesseract and Tesseract OCR to be installed.

        Args:
            filepath: Path to image file

        Returns:
            OCR-extracted text
        """
        try:
            import pytesseract
            from PIL import Image

            img = Image.open(filepath)
            text = pytesseract.image_to_string(img)
            return text.strip()

        except ImportError:
            logger.debug("pytesseract or PIL not installed, skipping OCR")
            return ""
        except Exception as e:
            logger.error(f"OCR failed for {filepath}: {e}")
            return ""


# Singleton instance
_processor_instance: Optional[AttachmentProcessor] = None


def get_attachment_processor() -> AttachmentProcessor:
    """
    Get singleton AttachmentProcessor instance.

    Returns:
        AttachmentProcessor instance
    """
    global _processor_instance

    if _processor_instance is None:
        _processor_instance = AttachmentProcessor()

    return _processor_instance
