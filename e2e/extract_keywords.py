#!/usr/bin/env python3
"""Extract keywords from OpenFrame manuals for E2E testing"""
import sys
import io
import json
import re
import requests
from collections import Counter

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

# Login
resp = requests.post('http://localhost:9000/api/v1/auth/login',
    json={'username': 'admin', 'password': 'SecureAdm1nP@ss2024!'})
token = resp.json()['data']['access_token']
headers = {'Authorization': f'Bearer {token}'}

print("Extracting keywords from OpenFrame manuals...")

# Get all documents
docs_resp = requests.get('http://localhost:9000/api/v1/documents', headers=headers).json()
documents = docs_resp.get('data', {}).get('documents', [])

print(f"Found {len(documents)} documents")

# Keywords to extract - OpenFrame specific terms
keywords = set()

# 1. Extract command names (ending with mgr, ctl, etc.)
command_patterns = [
    r'\b([a-z]+mgr)\b',      # *mgr commands
    r'\b([a-z]+ctl)\b',       # *ctl commands
    r'\b(tj[a-z]+)\b',        # tj* commands (TJES related)
    r'\b(of[a-z]+)\b',        # of* commands
    r'\b(ds[a-z]+)\b',        # ds* commands (dataset)
]

# 2. Known OpenFrame keywords
openframe_keywords = [
    # Core products
    'OpenFrame', 'TJES', 'TACF', 'HiDB', 'NDB', 'OSC', 'OSI',
    'TSAM', 'VSAM', 'JCL', 'COBOL', 'PL/I', 'Assembler',

    # Commands - mgr series
    'tjesmgr', 'tacfmgr', 'hidbmgr', 'ndbmgr', 'oscmgr', 'osimgr',
    'ofmgr', 'volmgr', 'catmgr', 'dsmigin', 'dsmigout',
    'jesinit', 'jesdown', 'tjclrun', 'textrun', 'protrn',

    # Utilities
    'idcams', 'iebgener', 'iebcopy', 'iefbr14', 'sort', 'dfsort',
    'ikjeft01', 'ikjeft1b', 'irxjcl', 'rexx',

    # JCL keywords
    'JOB', 'EXEC', 'DD', 'PROC', 'PEND', 'INCLUDE', 'JCLLIB',
    'STEPLIB', 'JOBLIB', 'SYSOUT', 'SYSIN', 'SYSPRINT',

    # Error codes (will search for patterns)
    'ABEND', 'S0C7', 'S0C4', 'S0C1', 'S806', 'S013', 'S322',

    # Configuration
    'oframe.conf', 'tjes.conf', 'tacf.conf', 'osc.conf',
    'ds.conf', 'hidb.conf', 'print.conf', 'saf.conf',

    # Regions/Subsystems
    'CICS', 'IMS', 'DB2', 'MQ', 'TSO', 'ISPF', 'VTAM',

    # Data types
    'PDS', 'PDSE', 'PS', 'KSDS', 'ESDS', 'RRDS', 'LDS',
    'GDG', 'ALIAS', 'CLUSTER', 'AIX',

    # Parameters
    'DISP', 'DCB', 'SPACE', 'UNIT', 'VOL', 'LABEL',
    'RECFM', 'LRECL', 'BLKSIZE', 'DSORG', 'KEYLEN',

    # Migration/Conversion
    'migration', 'conversion', 'rehosting', 'modernization',

    # Japanese terms (common in manuals)
    'コマンド', 'ユーティリティ', 'パラメータ', 'オプション',
    'エラー', '設定', '環境', 'ジョブ', 'データセット',
]

# Add known keywords
for kw in openframe_keywords:
    if len(kw) >= 3:
        keywords.add(kw)

# 3. Search for more keywords in document content via API
# Search for common patterns
search_queries = [
    'mgr command',
    'utility reference',
    'error code',
    'configuration',
    'parameter',
]

for query in search_queries:
    try:
        result = requests.post(
            'http://localhost:9000/api/v1/agents/execute',
            json={'task': f'List all {query} names', 'agent_type': 'rag', 'language': 'en'},
            headers=headers,
            timeout=60
        ).json()

        answer = result.get('answer', '')
        # Extract potential keywords from answer
        words = re.findall(r'\b([a-zA-Z][a-zA-Z0-9_]{2,20})\b', answer)
        for word in words:
            if len(word) >= 3 and word.lower() not in ['the', 'and', 'for', 'that', 'this', 'with']:
                keywords.add(word)
    except Exception as e:
        print(f"Error searching '{query}': {e}")

# 4. Add error code patterns
error_prefixes = ['BASE', 'TJES', 'TACF', 'OSC', 'OSI', 'NDB', 'HIDB', 'TSAM', 'OFCOM']
for prefix in error_prefixes:
    keywords.add(f'{prefix} error')
    keywords.add(f'{prefix} -5000')

# 5. Add specific technical terms
technical_terms = [
    # Commands with specific functions
    'tjclrun', 'textrun', 'ofruisvr', 'ofrdmsvr', 'ofrlhsvr',
    'ofgwmain', 'ofgwenv', 'obmtsmgr', 'obmjmsvr', 'obmjschd',
    'ofsys', 'ofboot', 'ofdown', 'tmboot', 'tmdown',

    # Batch processing
    'job scheduling', 'job class', 'job priority', 'job queue',
    'step execution', 'condition code', 'return code',

    # Dataset operations
    'dataset allocation', 'dataset delete', 'dataset rename',
    'catalog', 'uncatalog', 'scratch', 'retain',

    # Security
    'RACF', 'security', 'permission', 'access control',
    'user authentication', 'resource protection',

    # Network/Online
    'terminal', 'session', 'transaction', 'program',
    'map', 'mapset', 'BMS', 'screen',

    # System management
    'region', 'address space', 'task', 'TCB', 'SRB',
    'storage', 'memory', 'buffer', 'pool',
]

for term in technical_terms:
    keywords.add(term)

# Convert to list and sort
keyword_list = sorted(list(keywords), key=lambda x: x.lower())

# Limit to 300 most relevant
# Prioritize: commands (*mgr), error codes, configuration, then others
priority_keywords = []
other_keywords = []

for kw in keyword_list:
    kw_lower = kw.lower()
    if any(pattern in kw_lower for pattern in ['mgr', 'ctl', 'error', 'conf', 'tjes', 'tacf', 'jcl', 'dataset']):
        priority_keywords.append(kw)
    else:
        other_keywords.append(kw)

# Combine: priority first, then others
final_keywords = priority_keywords + other_keywords
final_keywords = final_keywords[:300]

print(f"\nExtracted {len(final_keywords)} keywords")
print("\nSample keywords:")
for i, kw in enumerate(final_keywords[:30]):
    print(f"  {i+1}. {kw}")

# Save to file
output = {
    'total': len(final_keywords),
    'keywords': final_keywords
}

with open('keywords.json', 'w', encoding='utf-8') as f:
    json.dump(output, f, ensure_ascii=False, indent=2)

print(f"\nSaved to keywords.json")
