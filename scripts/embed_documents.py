"""
Document Embedding Script
Embeds documents via the API for RAG testing.
"""
import requests
import time
import json

API_BASE_URL = "http://localhost:9000/api/v1"
ADMIN_USERNAME = "admin"
ADMIN_PASSWORD = "SecureAdm1nP@ss2024!"

def main():
    print("=" * 60)
    print("Document Embedding Script")
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
        return

    login_data = login_resp.json()
    if not login_data.get("success"):
        print(f"[FAIL] Login failed: {login_data}")
        return

    token = login_data.get("data", {}).get("access_token")
    if not token:
        print(f"[FAIL] No token in response: {login_data}")
        return

    print(f"[OK] Logged in as {ADMIN_USERNAME}")

    headers = {"Authorization": f"Bearer {token}"}

    # Step 2: Get documents list
    print("\n[Step 2] Getting documents list...")
    docs_resp = requests.get(f"{API_BASE_URL}/documents", headers=headers)

    if docs_resp.status_code != 200:
        print(f"[FAIL] Failed to get documents: {docs_resp.status_code}")
        print(docs_resp.text)
        return

    docs_data = docs_resp.json()
    documents = docs_data.get("documents", docs_data) if isinstance(docs_data, dict) else docs_data

    if not documents:
        print("[INFO] No documents found. Please upload documents first at http://localhost:3000/documents")
        return

    print(f"[OK] Found {len(documents)} document(s)")
    print()

    # Display documents
    not_embedded = []
    for doc in documents:
        doc_id = doc.get("id", "N/A")
        title = doc.get("title", doc.get("name", "Unknown"))
        is_embedded = doc.get("is_embedded", doc.get("embedded", False))
        chunk_count = doc.get("chunk_count", doc.get("chunks", 0))
        status = "[EMBEDDED]" if is_embedded else "[NOT EMBEDDED]"

        print(f"  {status} {title[:50]}")
        print(f"           ID: {doc_id[:16]}... | Chunks: {chunk_count}")

        if not is_embedded:
            not_embedded.append(doc)

    print()

    if not not_embedded:
        print("[OK] All documents are already embedded!")
        return

    # Step 3: Embed documents
    print(f"\n[Step 3] Embedding {len(not_embedded)} document(s)...")

    for doc in not_embedded:
        doc_id = doc.get("id")
        title = doc.get("title", doc.get("name", "Unknown"))

        print(f"\n  Embedding: {title[:50]}...")

        # Trigger embedding
        embed_resp = requests.post(
            f"{API_BASE_URL}/documents/{doc_id}/embed",
            headers=headers,
            timeout=300  # 5 minutes timeout for large documents
        )

        if embed_resp.status_code == 200:
            result = embed_resp.json()
            chunks = result.get("chunk_count", result.get("chunks", "?"))
            print(f"  [OK] Embedded successfully! Chunks: {chunks}")
        else:
            print(f"  [FAIL] Embedding failed: {embed_resp.status_code}")
            try:
                print(f"         {embed_resp.json()}")
            except:
                print(f"         {embed_resp.text[:200]}")

    # Step 4: Verify embedding
    print("\n[Step 4] Verifying embedding status...")
    time.sleep(2)  # Wait for indexing

    docs_resp = requests.get(f"{API_BASE_URL}/documents", headers=headers)
    docs_data = docs_resp.json()
    documents = docs_data.get("documents", docs_data) if isinstance(docs_data, dict) else docs_data

    embedded_count = 0
    total_chunks = 0

    for doc in documents:
        is_embedded = doc.get("is_embedded", doc.get("embedded", False))
        chunk_count = doc.get("chunk_count", doc.get("chunks", 0))
        if is_embedded:
            embedded_count += 1
            total_chunks += chunk_count

    print()
    print("=" * 60)
    print("Summary")
    print("=" * 60)
    print(f"  Total documents: {len(documents)}")
    print(f"  Embedded: {embedded_count}")
    print(f"  Total chunks: {total_chunks}")
    print("=" * 60)

    if embedded_count == len(documents):
        print("\n[OK] All documents embedded successfully!")
        print("     You can now test RAG at http://localhost:3000/agent")
    else:
        print(f"\n[WARN] {len(documents) - embedded_count} document(s) still not embedded")


if __name__ == "__main__":
    main()
