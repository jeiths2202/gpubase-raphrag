"""
Image Preprocessor Service

Handles image extraction, preprocessing, and optimization for Vision LLM processing.
Supports PDF, Office documents, and direct image uploads.
"""

import asyncio
import io
import logging
from pathlib import Path
from typing import List, Optional, Tuple

from PIL import Image

from app.api.models.vision import (
    BoundingBox,
    ImageType,
    ProcessedImage,
)

logger = logging.getLogger(__name__)


class ImagePreprocessor:
    """
    Image preprocessing pipeline for Vision LLM.

    Features:
    - Format conversion (to PNG/JPEG)
    - Dimension resizing (respecting aspect ratio)
    - Quality optimization
    - PDF page rendering
    - Embedded image extraction
    """

    # Processing limits
    MAX_IMAGE_DIMENSION = 2048
    MAX_FILE_SIZE = 20 * 1024 * 1024  # 20MB
    DEFAULT_DPI = 150
    JPEG_QUALITY = 85

    # Supported formats
    SUPPORTED_INPUT_FORMATS = {
        "PNG", "JPEG", "JPG", "GIF", "WEBP", "BMP", "TIFF"
    }
    SUPPORTED_OUTPUT_FORMATS = {"PNG", "JPEG"}

    def __init__(
        self,
        max_dimension: int = 2048,
        default_format: str = "PNG",
        jpeg_quality: int = 85,
    ):
        """
        Initialize preprocessor.

        Args:
            max_dimension: Maximum width/height for processed images
            default_format: Default output format (PNG or JPEG)
            jpeg_quality: JPEG compression quality (1-100)
        """
        self.max_dimension = max_dimension
        self.default_format = default_format.upper()
        self.jpeg_quality = jpeg_quality

    async def preprocess(
        self,
        image_bytes: bytes,
        target_format: Optional[str] = None,
        max_dimension: Optional[int] = None,
    ) -> ProcessedImage:
        """
        Preprocess a single image.

        Args:
            image_bytes: Raw image bytes
            target_format: Output format (PNG/JPEG)
            max_dimension: Max width/height override

        Returns:
            ProcessedImage ready for Vision LLM
        """
        target_format = (target_format or self.default_format).upper()
        max_dim = max_dimension or self.max_dimension

        # Open image
        image = Image.open(io.BytesIO(image_bytes))
        original_size = image.size
        original_format = image.format or "UNKNOWN"

        # Convert mode if necessary (for JPEG compatibility)
        if target_format == "JPEG" and image.mode in ("RGBA", "P"):
            # Create white background for transparency
            background = Image.new("RGB", image.size, (255, 255, 255))
            if image.mode == "P":
                image = image.convert("RGBA")
            background.paste(image, mask=image.split()[-1] if image.mode == "RGBA" else None)
            image = background
        elif image.mode not in ("RGB", "RGBA", "L"):
            image = image.convert("RGB")

        # Resize if needed
        processed_size = original_size
        if image.size[0] > max_dim or image.size[1] > max_dim:
            image = self._resize_maintain_aspect(image, max_dim)
            processed_size = image.size

        # Convert to bytes
        output = io.BytesIO()
        save_kwargs = {"format": target_format}
        if target_format == "JPEG":
            save_kwargs["quality"] = self.jpeg_quality
            save_kwargs["optimize"] = True
        elif target_format == "PNG":
            save_kwargs["optimize"] = True

        image.save(output, **save_kwargs)
        processed_bytes = output.getvalue()

        # Calculate compression ratio
        compression_ratio = len(image_bytes) / len(processed_bytes) if processed_bytes else 1.0

        # Determine MIME type
        mime_type = f"image/{target_format.lower()}"
        if target_format == "JPEG":
            mime_type = "image/jpeg"

        return ProcessedImage(
            image_bytes=processed_bytes,
            mime_type=mime_type,
            original_size=original_size,
            processed_size=processed_size,
            format=target_format,
            compression_ratio=compression_ratio,
        )

    async def extract_from_pdf(
        self,
        pdf_path: Path,
        dpi: int = None,
        page_numbers: Optional[List[int]] = None,
    ) -> List[ProcessedImage]:
        """
        Extract images from PDF pages.

        Args:
            pdf_path: Path to PDF file
            dpi: Resolution for page rendering
            page_numbers: Specific pages to extract (None = all)

        Returns:
            List of ProcessedImage, one per page
        """
        dpi = dpi or self.DEFAULT_DPI
        images = []

        try:
            # Try pdf2image (requires poppler)
            from pdf2image import convert_from_path

            pages = convert_from_path(
                str(pdf_path),
                dpi=dpi,
                fmt="PNG",
                first_page=page_numbers[0] if page_numbers else None,
                last_page=page_numbers[-1] if page_numbers else None,
            )

            for i, page in enumerate(pages):
                page_num = page_numbers[i] if page_numbers else i + 1

                # Convert PIL Image to bytes
                page_bytes = self._pil_to_bytes(page, "PNG")

                # Preprocess
                processed = await self.preprocess(page_bytes)
                processed.page_number = page_num
                processed.image_type = ImageType.PAGE

                images.append(processed)

        except ImportError:
            logger.warning("pdf2image not available, trying PyMuPDF")
            images = await self._extract_pdf_pymupdf(pdf_path, dpi, page_numbers)

        except Exception as e:
            logger.error(f"PDF extraction error: {e}")
            raise

        return images

    async def _extract_pdf_pymupdf(
        self,
        pdf_path: Path,
        dpi: int,
        page_numbers: Optional[List[int]] = None,
    ) -> List[ProcessedImage]:
        """Extract PDF pages using PyMuPDF (fitz)."""
        images = []

        try:
            import fitz  # PyMuPDF

            doc = fitz.open(str(pdf_path))
            zoom = dpi / 72  # Default PDF DPI is 72

            pages_to_process = page_numbers or range(1, len(doc) + 1)

            for page_num in pages_to_process:
                page = doc[page_num - 1]  # 0-indexed
                mat = fitz.Matrix(zoom, zoom)
                pix = page.get_pixmap(matrix=mat)

                # Convert to PNG bytes
                page_bytes = pix.tobytes("png")

                # Preprocess
                processed = await self.preprocess(page_bytes)
                processed.page_number = page_num
                processed.image_type = ImageType.PAGE

                images.append(processed)

            doc.close()

        except ImportError:
            logger.error("Neither pdf2image nor PyMuPDF available for PDF extraction")
            raise RuntimeError("PDF extraction requires pdf2image or PyMuPDF")

        return images

    async def extract_embedded_images(
        self,
        pdf_path: Path,
        min_size: Tuple[int, int] = (100, 100),
    ) -> List[ProcessedImage]:
        """
        Extract embedded images from PDF.

        Args:
            pdf_path: Path to PDF file
            min_size: Minimum image dimensions to extract

        Returns:
            List of ProcessedImage for embedded images
        """
        images = []

        try:
            import fitz  # PyMuPDF

            doc = fitz.open(str(pdf_path))

            for page_num in range(len(doc)):
                page = doc[page_num]
                image_list = page.get_images(full=True)

                for img_index, img in enumerate(image_list):
                    xref = img[0]
                    base_image = doc.extract_image(xref)

                    if base_image:
                        image_bytes = base_image["image"]
                        image_ext = base_image["ext"]

                        # Check minimum size
                        pil_image = Image.open(io.BytesIO(image_bytes))
                        if pil_image.size[0] < min_size[0] or pil_image.size[1] < min_size[1]:
                            continue

                        # Preprocess
                        processed = await self.preprocess(image_bytes)
                        processed.page_number = page_num + 1
                        processed.image_type = ImageType.EMBEDDED

                        images.append(processed)

            doc.close()

        except ImportError:
            logger.warning("PyMuPDF not available for embedded image extraction")
        except Exception as e:
            logger.error(f"Embedded image extraction error: {e}")

        return images

    async def process_batch(
        self,
        image_bytes_list: List[bytes],
        target_format: Optional[str] = None,
    ) -> List[ProcessedImage]:
        """
        Process multiple images in parallel.

        Args:
            image_bytes_list: List of raw image bytes
            target_format: Output format for all images

        Returns:
            List of ProcessedImage
        """
        tasks = [
            self.preprocess(img_bytes, target_format)
            for img_bytes in image_bytes_list
        ]

        results = await asyncio.gather(*tasks, return_exceptions=True)

        processed_images = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                logger.error(f"Batch preprocessing error for image {i}: {result}")
            else:
                processed_images.append(result)

        return processed_images

    def _resize_maintain_aspect(
        self,
        image: Image.Image,
        max_dimension: int,
    ) -> Image.Image:
        """Resize image maintaining aspect ratio."""
        width, height = image.size

        if width > height:
            new_width = max_dimension
            new_height = int(height * (max_dimension / width))
        else:
            new_height = max_dimension
            new_width = int(width * (max_dimension / height))

        return image.resize(
            (new_width, new_height),
            Image.Resampling.LANCZOS
        )

    def _pil_to_bytes(
        self,
        image: Image.Image,
        format: str = "PNG",
    ) -> bytes:
        """Convert PIL Image to bytes."""
        output = io.BytesIO()
        save_kwargs = {"format": format}
        if format == "JPEG":
            save_kwargs["quality"] = self.jpeg_quality
        image.save(output, **save_kwargs)
        return output.getvalue()

    def validate_image(self, image_bytes: bytes) -> dict:
        """
        Validate image bytes.

        Returns:
            Dict with validation result and image info
        """
        try:
            image = Image.open(io.BytesIO(image_bytes))

            # Check format
            if image.format and image.format.upper() not in self.SUPPORTED_INPUT_FORMATS:
                return {
                    "valid": False,
                    "reason": f"Unsupported format: {image.format}",
                }

            # Check size
            if len(image_bytes) > self.MAX_FILE_SIZE:
                return {
                    "valid": False,
                    "reason": f"File too large: {len(image_bytes) / 1024 / 1024:.1f}MB",
                }

            return {
                "valid": True,
                "format": image.format,
                "size": image.size,
                "mode": image.mode,
                "file_size": len(image_bytes),
            }

        except Exception as e:
            return {
                "valid": False,
                "reason": f"Invalid image: {str(e)}",
            }

    def estimate_processing_cost(
        self,
        image_bytes: bytes,
        target_format: str = "PNG",
    ) -> dict:
        """
        Estimate processing requirements.

        Returns:
            Dict with estimated output size and processing time
        """
        try:
            image = Image.open(io.BytesIO(image_bytes))
            original_size = image.size
            file_size = len(image_bytes)

            # Estimate output dimensions
            if original_size[0] > self.max_dimension or original_size[1] > self.max_dimension:
                ratio = min(
                    self.max_dimension / original_size[0],
                    self.max_dimension / original_size[1]
                )
                output_size = (
                    int(original_size[0] * ratio),
                    int(original_size[1] * ratio)
                )
            else:
                output_size = original_size

            # Estimate output file size (rough approximation)
            pixels = output_size[0] * output_size[1]
            if target_format == "JPEG":
                estimated_size = pixels * 0.1  # ~0.1 bytes per pixel for JPEG
            else:
                estimated_size = pixels * 0.5  # ~0.5 bytes per pixel for PNG

            return {
                "original_size": original_size,
                "output_size": output_size,
                "original_file_size": file_size,
                "estimated_output_size": int(estimated_size),
                "requires_resize": original_size != output_size,
            }

        except Exception as e:
            return {
                "error": str(e),
            }
