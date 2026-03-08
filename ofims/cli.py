"""OFIMS CLI - IMS Semantic Search Command Line Interface"""
import argparse
import sys

from .client import IMSClient
from .config import API_BASE_URL, AUTH_USERNAME, AUTH_PASSWORD
from . import display


def main():
    parser = argparse.ArgumentParser(
        prog="ofims",
        description="IMS Semantic Search CLI - BGE-M3 기반 자연어 IMS 이슈 검색",
    )
    parser.add_argument("--url", default=API_BASE_URL, help="API server URL")
    parser.add_argument("--user", default=AUTH_USERNAME, help="Username")
    parser.add_argument("--password", default=AUTH_PASSWORD, help="Password")

    sub = parser.add_subparsers(dest="command")

    # search
    p_search = sub.add_parser("search", help="Semantic search for IMS issues")
    p_search.add_argument("query", help="Natural language query")
    p_search.add_argument("--limit", type=int, default=10)
    p_search.add_argument("--product", default=None, help="Product filter")

    # detail
    p_detail = sub.add_parser("detail", help="Get full issue content")
    p_detail.add_argument("ims_id", help="IMS issue number")

    # related
    p_rel = sub.add_parser("related", help="Find related issues")
    p_rel.add_argument("ims_id", help="IMS issue number")

    # summarize
    p_sum = sub.add_parser("summarize", help="Summarize an issue")
    p_sum.add_argument("ims_id", help="IMS issue number")
    p_sum.add_argument("--lang", default="auto", help="Language: auto, ko, ja, en")

    # chat
    p_chat = sub.add_parser("chat", help="Chat with semantic search results")
    p_chat.add_argument("query", help="Natural language question")
    p_chat.add_argument("--limit", type=int, default=5, help="Search limit")
    p_chat.add_argument("--no-related", action="store_true", help="Skip related issues")
    p_chat.add_argument("--lang", default="auto", help="Language")

    # create-knowledge
    p_know = sub.add_parser("create-knowledge", help="Create knowledge from issues")
    p_know.add_argument("ims_ids", nargs="+", help="IMS issue numbers")
    p_know.add_argument("--title", required=True, help="Knowledge title")
    p_know.add_argument("--lang", default="auto", help="Language")

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        sys.exit(1)

    # Initialize client & login
    client = IMSClient(base_url=args.url)
    try:
        client.login(args.user, args.password)
    except Exception as e:
        print(f"  Login failed: {e}", file=sys.stderr)
        sys.exit(1)

    # Dispatch commands
    try:
        if args.command == "search":
            result = client.search(args.query, limit=args.limit, product=args.product)
            display.print_search_results(result)

        elif args.command == "detail":
            result = client.get_issue(args.ims_id)
            display.print_issue_detail(result)

        elif args.command == "related":
            result = client.get_related(args.ims_id)
            display.print_related_issues(result)

        elif args.command == "summarize":
            result = client.summarize(args.ims_id, language=args.lang)
            display.print_summary(result)

        elif args.command == "chat":
            events = client.chat_stream(
                args.query,
                limit=args.limit,
                include_related=not args.no_related,
                language=args.lang,
            )
            display.print_chat_stream(events)

        elif args.command == "create-knowledge":
            result = client.create_knowledge(args.ims_ids, title=args.title, language=args.lang)
            display.print_knowledge(result)

    except Exception as e:
        print(f"  Error: {e}", file=sys.stderr)
        sys.exit(1)
