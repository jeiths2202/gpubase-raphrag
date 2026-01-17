#!/usr/bin/env python3
"""
Standalone script to extract images from PDF and save to database.
Bypasses the full app initialization.
"""
import asyncio
import asyncpg
import fitz  # PyMuPDF
import os
import sys
from typing import List, Dict, Any

# Load environment variables from .env file manually
def load_env():
    env_path = "/opt/kms/.env"
    if os.path.exists(env_path):
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    # Handle lines with inline comments
                    if ' #' in line:
                        line = line.split(' #')[0].strip()
                    key, value = line.split('=', 1)
                    os.environ[key] = value

load_env()


async def extract_images(pdf_content: bytes, pdf_id: str, min_size: int = 50, max_images: int = 100) -> List[Dict[str, Any]]:
    """Extract images from PDF using PyMuPDF."""
    doc = fitz.open(stream=pdf_content, filetype="pdf")
    extracted_images = []

    for page_num in range(len(doc)):
        if len(extracted_images) >= max_images:
            break

        page = doc[page_num]
        image_list = page.get_images(full=True)

        for img_index, img_info in enumerate(image_list):
            if len(extracted_images) >= max_images:
                break

            xref = img_info[0]

            try:
                base_image = doc.extract_image(xref)
                if not base_image:
                    continue

                image_bytes = base_image["image"]
                width = base_image.get("width", 0)
                height = base_image.get("height", 0)

                # Skip small images
                if width < min_size or height < min_size:
                    continue

                # Determine mime type
                ext = base_image.get("ext", "png")
                mime_type = f"image/{ext}" if ext else "image/png"

                # Generate unique image ID
                image_id = f"{pdf_id}_p{page_num + 1}_img{img_index + 1}"

                # Get position on page
                rects = page.get_image_rects(xref)
                position = None
                if rects:
                    rect = rects[0]
                    position = {
                        "x0": rect.x0,
                        "y0": rect.y0,
                        "x1": rect.x1,
                        "y1": rect.y1
                    }

                extracted_images.append({
                    "document_id": pdf_id,
                    "image_id": image_id,
                    "page_number": page_num + 1,
                    "image_data": image_bytes,
                    "mime_type": mime_type,
                    "width": width,
                    "height": height,
                    "file_size": len(image_bytes),
                    "position": position
                })

            except Exception as e:
                print(f"Warning: Failed to extract image {xref}: {e}")
                continue

    doc.close()
    return extracted_images


async def save_images(pool, images: List[Dict[str, Any]]) -> int:
    """Save images to database."""
    import json
    import uuid
    from datetime import datetime, timezone

    if not images:
        return 0

    async with pool.acquire() as conn:
        saved_count = 0
        for img in images:
            try:
                position_json = json.dumps(img.get("position")) if img.get("position") else None

                await conn.execute("""
                    INSERT INTO image_embeddings (
                        id, document_id, image_id, page_number,
                        image_data, mime_type, width, height, file_size,
                        position, created_at, updated_at
                    ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $11)
                    ON CONFLICT (image_id) DO UPDATE SET
                        image_data = EXCLUDED.image_data,
                        mime_type = EXCLUDED.mime_type,
                        width = EXCLUDED.width,
                        height = EXCLUDED.height,
                        file_size = EXCLUDED.file_size,
                        position = EXCLUDED.position,
                        updated_at = EXCLUDED.updated_at
                """,
                    uuid.uuid4(),
                    img["document_id"],
                    img["image_id"],
                    img["page_number"],
                    img["image_data"],
                    img["mime_type"],
                    img["width"],
                    img["height"],
                    img["file_size"],
                    position_json,
                    datetime.now(timezone.utc)
                )
                saved_count += 1
            except Exception as e:
                print(f"Failed to save image {img.get('image_id')}: {e}")

        return saved_count


async def main():
    # Configuration
    pdf_path = "/opt/kms/OF_OSI_7.2_MFS-Reference-Guide_v3.1.2_jp.pdf"
    pdf_id = "pdf_98df7baa256f"

    # Read PDF
    print(f"Reading PDF: {pdf_path}")
    with open(pdf_path, 'rb') as f:
        pdf_content = f.read()
    print(f"PDF size: {len(pdf_content)} bytes")

    # Extract images
    print("Extracting images...")
    images = await extract_images(pdf_content, pdf_id, min_size=50, max_images=100)
    print(f"Extracted {len(images)} images")

    if not images:
        print("No images found in PDF")
        return

    # Show extracted images
    for img in images[:10]:
        print(f"  - {img['image_id']} (page {img['page_number']}, {img['width']}x{img['height']}, {img['file_size']} bytes)")

    if len(images) > 10:
        print(f"  ... and {len(images) - 10} more")

    # Connect to database
    print("\nConnecting to database...")
    pool = await asyncpg.create_pool(
        host=os.environ.get('POSTGRES_HOST', 'localhost'),
        port=int(os.environ.get('POSTGRES_PORT', 5432)),
        user=os.environ.get('POSTGRES_USER', 'postgres'),
        password=os.environ.get('POSTGRES_PASSWORD', 'postgres'),
        database=os.environ.get('POSTGRES_DB', 'kms'),
        min_size=1,
        max_size=5
    )

    # Save images
    print("Saving images to database...")
    saved = await save_images(pool, images)
    print(f"Saved {saved} images to database")

    # Cleanup
    await pool.close()
    print("\nDone!")


if __name__ == "__main__":
    asyncio.run(main())
