"""
CLI script for query resolution.
Spawned by Express backend: python resolve_query.py "How is Apple doing?"
Outputs JSON to stdout.
"""

import sys
import json

from services.query_resolver import resolve_query


def main():
    if len(sys.argv) < 2:
        result = {
            "ticker": None,
            "error": "Usage: python resolve_query.py <query>",
            "resolved": False,
            "confidence": 0.0,
        }
        print(json.dumps(result))
        sys.exit(1)

    query = " ".join(sys.argv[1:])
    result = resolve_query(query)
    print(json.dumps(result))


if __name__ == "__main__":
    main()
