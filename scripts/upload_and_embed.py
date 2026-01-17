"""
Upload and Embed Documents Script
Uploads PDF files and triggers embedding for RAG testing.
"""
import requests
import time
import os
import sys

API_BASE_URL = "http://localhost:9000/api/v1"
ADMIN_USERNAME = "admin"
ADMIN_PASSWORD = "SecureAdm1nP@ss2024!"

# PDF files to upload (in project root)
PDF_FILES = [
    "OF_Base_7.1_Installation-Guide_v3.1.2_kr.pdf",
    "OF_OSI_7.2_MFS-Reference-Guide_v3.1.2_kr.pdf",
]

def main():
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    print("=" * 60)
    print("Upload and Embed Documents")
    print("=" * 60)

    # Step 1: Login
    print("\n[Step 1] Logging in...")
    login_resp = requests.post(
        f"{API_BASE_URL}/auth/login",
        json={"username": ADMIN_USERNAME, "password": ADMIN_PASSWORD}
    )

    if login_resp.status_code != 200:
        print(f"[FAIL] Login failed: {login_resp.status_code}")
        print(login_resp.text)
        return 1

    login_data = login_resp.json()
    if not login_data.get("success"):
        print(f"[FAIL] Login failed: {login_data}")
        return 1

    token = login_data.get("data", {}).get("access_token")
    print(f"[OK] Logged in as {ADMIN_USERNAME}")

    headers = {"Authorization": f"Bearer {token}"}

    # Step 2: Upload documents
    print("\n[Step 2] Uploading documents...")

    uploaded_docs = []
    for pdf_name in PDF_FILES:
        pdf_path = os.path.join(project_root, pdf_name)

        if not os.path.exists(pdf_path):
            print(f"  [SKIP] {pdf_name} - File not found")
            continue

        file_size = os.path.getsize(pdf_path) / (1024 * 1024)  # MB
        print(f"\n  Uploading: {pdf_name} ({file_size:.1f} MB)...")

        with open(pdf_path, "rb") as f:
            files = {"file": (pdf_name, f, "application/pdf")}
            data = {
                "language": "ko",
                "processing_mode": "text_only",
                "enable_vlm": "false",
                "extract_tables": "true",
                "extract_images": "true"
            }

            upload_resp = requests.post(
                f"{API_BASE_URL}/documents",
                headers=headers,
                files=files,
                data=data,
                timeout=300
            )

        if upload_resp.status_code in [200, 201, 202]:
            result = upload_resp.json()
            doc_id = result.get("data", {}).get("document_id") or result.get("data", {}).get("id")
            if doc_id:
                print(f"  [OK] Uploaded! Document ID: {doc_id[:16]}...")
                uploaded_docs.append({"id": doc_id, "name": pdf_name})
            else:
                print(f"  [OK] Upload response: {result}")
        else:
            print(f"  [FAIL] Upload failed: {upload_resp.status_code}")
            try:
                error_detail = upload_resp.json()
                print(f"         {error_detail}")
            except:
                print(f"         {upload_resp.text[:300]}")

    if not uploaded_docs:
        print("\n[INFO] No new documents uploaded.")
        # Check existing documents
        docs_resp = requests.get(f"{API_BASE_URL}/documents", headers=headers)
        if docs_resp.status_code == 200:
            docs_data = docs_resp.json()
            existing = docs_data.get("data", {}).get("documents", [])
            if existing:
                print(f"[INFO] Found {len(existing)} existing documents:")
                for doc in existing:
                    print(f"  - {doc.get('name', doc.get('title', 'Unknown'))}")
                    uploaded_docs.append({"id": doc.get("id"), "name": doc.get("name")})

    # Step 3: Wait for processing
    if uploaded_docs:
        print("\n[Step 3] Waiting for document processing...")
        time.sleep(5)  # Give some time for initial processing

        # Step 4: Trigger embedding
        print("\n[Step 4] Triggering embedding...")

        for doc in uploaded_docs:
            doc_id = doc.get("id")
            doc_name = doc.get("name", "Unknown")

            if not doc_id:
                continue

            print(f"\n  Embedding: {doc_name}...")

            # Check document status first
            status_resp = requests.get(
                f"{API_BASE_URL}/documents/{doc_id}",
                headers=headers
            )

            if status_resp.status_code == 200:
                status_data = status_resp.json()
                doc_info = status_data.get("data", status_data)
                is_embedded = doc_info.get("is_embedded", False)

                if is_embedded:
                    chunks = doc_info.get("chunk_count", 0)
                    print(f"  [OK] Already embedded! Chunks: {chunks}")
                    continue

            # Trigger embedding
            embed_resp = requests.post(
                f"{API_BASE_URL}/documents/{doc_id}/embed",
                headers=headers,
                timeout=600  # 10 minutes for large documents
            )

            if embed_resp.status_code == 200:
                result = embed_resp.json()
                chunks = result.get("data", {}).get("chunk_count", result.get("chunk_count", "?"))
                print(f"  [OK] Embedded! Chunks: {chunks}")
            elif embed_resp.status_code == 202:
                print(f"  [OK] Embedding started (processing in background)")
            else:
                print(f"  [FAIL] Embedding failed: {embed_resp.status_code}")
                try:
                    print(f"         {embed_resp.json()}")
                except:
                    print(f"         {embed_resp.text[:300]}")

    # Step 5: Verify final status
    print("\n[Step 5] Verifying final status...")
    time.sleep(3)

    docs_resp = requests.get(f"{API_BASE_URL}/documents", headers=headers)
    if docs_resp.status_code == 200:
        docs_data = docs_resp.json()
        documents = docs_data.get("data", {}).get("documents", [])

        print("\n" + "=" * 60)
        print("Final Document Status")
        print("=" * 60)

        total_chunks = 0
        embedded_count = 0

        for doc in documents:
            name = doc.get("name", doc.get("title", "Unknown"))
            is_embedded = doc.get("is_embedded", False)
            chunks = doc.get("chunk_count", 0)
            status = "[EMBEDDED]" if is_embedded else "[PENDING]"

            print(f"  {status} {name[:45]}")
            print(f"           Chunks: {chunks}")

            if is_embedded:
                embedded_count += 1
                total_chunks += chunks

        print()
        print(f"  Total Documents: {len(documents)}")
        print(f"  Embedded: {embedded_count}")
        print(f"  Total Chunks: {total_chunks}")
        print("=" * 60)

        if embedded_count > 0:
            print("\n[OK] Documents ready for RAG testing!")
            print("     Test at: http://localhost:3000/agent")
            return 0
        else:
            print("\n[WARN] No documents embedded yet. Processing may be ongoing.")
            return 1
    else:
        print(f"[FAIL] Could not verify status: {docs_resp.status_code}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
