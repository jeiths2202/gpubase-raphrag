#!/usr/bin/env python3
"""
Graph DB Data Quality Issue Fixer

Fixes issues found by graph_db_quality_test.py:
1. Document nodes missing filename (copy from title)
2. Entity nodes missing type (infer from name patterns)

Usage:
    python scripts/fix_graph_db_issues.py [--dry-run]
"""

import os
import sys
import re
import argparse
from typing import Dict, List, Tuple
from dotenv import load_dotenv

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from neo4j import GraphDatabase


# Entity type inference patterns
ENTITY_TYPE_PATTERNS: List[Tuple[str, str, str]] = [
    # (pattern, type, description)
    (r'^[A-Z]{2,}_[A-Z0-9_]+$', 'COMMAND', 'Uppercase with underscores (e.g., STATUS, OFASM)'),
    (r'^[a-z]+_[a-z]+$', 'PERSON', 'Lowercase with underscore (e.g., soyoung_lee)'),
    (r'^[A-Z][a-z]+[A-Z][a-z]+', 'CONCEPT', 'CamelCase'),
    (r'^\d+$', 'NUMBER', 'Pure numbers'),
    (r'^-?\d{4,5}$', 'ERROR_CODE', 'Error codes like -5212'),
    (r'^[A-Z]{2,6}$', 'ACRONYM', 'Short uppercase (e.g., JCL, VSAM)'),
    (r'mgr$', 'MANAGER_COMMAND', 'Manager commands (e.g., tjesmgr)'),
    (r'\.conf$', 'CONFIG_FILE', 'Config files'),
    (r'^[A-Z][a-z]+$', 'PROPER_NOUN', 'Capitalized word'),
]

# Default type if no pattern matches
DEFAULT_ENTITY_TYPE = 'CONCEPT'


def infer_entity_type(name: str) -> str:
    """Infer entity type from name patterns."""
    if not name:
        return DEFAULT_ENTITY_TYPE

    for pattern, entity_type, _ in ENTITY_TYPE_PATTERNS:
        if re.match(pattern, name):
            return entity_type

    return DEFAULT_ENTITY_TYPE


class GraphDBFixer:
    """Fixes data quality issues in Neo4j Graph DB."""

    def __init__(self, uri: str, user: str, password: str, dry_run: bool = False):
        self.driver = GraphDatabase.driver(uri, auth=(user, password))
        self.dry_run = dry_run
        self.fixes_applied = {
            'document_filename': 0,
            'entity_type': 0
        }

    def close(self):
        self.driver.close()

    def fix_document_filename(self) -> int:
        """Fix Document nodes missing filename by copying from title."""
        print("\n" + "=" * 60)
        print("Fix 1: Document nodes missing filename")
        print("=" * 60)

        with self.driver.session() as session:
            # Find documents missing filename
            result = session.run("""
                MATCH (d:Document)
                WHERE d.filename IS NULL AND d.title IS NOT NULL
                RETURN d.id as id, d.title as title
            """)

            docs_to_fix = [(r['id'], r['title']) for r in result]

            if not docs_to_fix:
                print("  No documents need fixing.")
                return 0

            print(f"  Found {len(docs_to_fix)} document(s) to fix:")
            for doc_id, title in docs_to_fix:
                print(f"    - {doc_id}: title='{title}' -> filename='{title}'")

            if self.dry_run:
                print("  [DRY-RUN] Would fix these documents.")
                return len(docs_to_fix)

            # Apply fix
            result = session.run("""
                MATCH (d:Document)
                WHERE d.filename IS NULL AND d.title IS NOT NULL
                SET d.filename = d.title
                RETURN count(d) as fixed
            """)

            fixed = result.single()['fixed']
            print(f"  [FIXED] {fixed} document(s) updated.")
            self.fixes_applied['document_filename'] = fixed
            return fixed

    def fix_entity_type(self) -> int:
        """Fix Entity nodes missing type by inferring from name patterns."""
        print("\n" + "=" * 60)
        print("Fix 2: Entity nodes missing type")
        print("=" * 60)

        with self.driver.session() as session:
            # Get entities missing type
            result = session.run("""
                MATCH (e:Entity)
                WHERE e.type IS NULL AND e.name IS NOT NULL
                RETURN e.name as name
            """)

            entities = [r['name'] for r in result]

            if not entities:
                print("  No entities need fixing.")
                return 0

            print(f"  Found {len(entities)} entities to fix.")

            # Group by inferred type
            type_groups: Dict[str, List[str]] = {}
            for name in entities:
                inferred_type = infer_entity_type(name)
                if inferred_type not in type_groups:
                    type_groups[inferred_type] = []
                type_groups[inferred_type].append(name)

            print("\n  Type inference summary:")
            for entity_type, names in sorted(type_groups.items(), key=lambda x: -len(x[1])):
                sample = names[:3]
                sample_str = ', '.join(sample)
                if len(names) > 3:
                    sample_str += f", ... (+{len(names)-3} more)"
                print(f"    {entity_type}: {len(names)} entities (e.g., {sample_str})")

            if self.dry_run:
                print("\n  [DRY-RUN] Would fix these entities.")
                return len(entities)

            # Apply fixes by type
            total_fixed = 0
            for entity_type, names in type_groups.items():
                result = session.run("""
                    MATCH (e:Entity)
                    WHERE e.name IN $names AND e.type IS NULL
                    SET e.type = $entity_type
                    RETURN count(e) as fixed
                """, names=names, entity_type=entity_type)

                fixed = result.single()['fixed']
                total_fixed += fixed

            print(f"\n  [FIXED] {total_fixed} entities updated.")
            self.fixes_applied['entity_type'] = total_fixed
            return total_fixed

    def run_all_fixes(self) -> Dict[str, int]:
        """Run all fixes and return summary."""
        print("\n" + "=" * 60)
        print("Graph DB Data Quality Fixer")
        print("=" * 60)

        if self.dry_run:
            print("[DRY-RUN MODE] No changes will be made.")

        self.fix_document_filename()
        self.fix_entity_type()

        print("\n" + "=" * 60)
        print("Summary")
        print("=" * 60)
        print(f"  Documents fixed: {self.fixes_applied['document_filename']}")
        print(f"  Entities fixed:  {self.fixes_applied['entity_type']}")
        print(f"  Total fixes:     {sum(self.fixes_applied.values())}")

        if self.dry_run:
            print("\n  [DRY-RUN] Run without --dry-run to apply fixes.")

        return self.fixes_applied


def main():
    parser = argparse.ArgumentParser(
        description='Fix Graph DB data quality issues'
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Show what would be fixed without making changes'
    )
    args = parser.parse_args()

    # Load environment
    load_dotenv()

    neo4j_uri = os.getenv('NEO4J_URI', 'bolt://localhost:7687')
    neo4j_user = os.getenv('NEO4J_USER', 'neo4j')
    neo4j_password = os.getenv('NEO4J_PASSWORD', '')

    if not neo4j_password:
        print("Error: NEO4J_PASSWORD not set in environment")
        sys.exit(1)

    fixer = GraphDBFixer(
        uri=neo4j_uri,
        user=neo4j_user,
        password=neo4j_password,
        dry_run=args.dry_run
    )

    try:
        fixer.run_all_fixes()
    finally:
        fixer.close()


if __name__ == '__main__':
    main()
