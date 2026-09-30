#!/usr/bin/env python3
"""Create a safe starter package for an Axiom agent implementation."""
from __future__ import annotations

import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from agent_sdk import scaffold_agent


def main() -> None:
    parser = argparse.ArgumentParser(description="Scaffold a versioned Axiom capability")
    parser.add_argument("implementation_key", help="Lowercase stable key such as supplier.lookup")
    parser.add_argument("--output", default="agents", help="Parent directory (default: agents)")
    parser.add_argument("--description", default="New Axiom capability")
    args = parser.parse_args()
    path = scaffold_agent(Path(args.output), args.implementation_key, description=args.description)
    print(path)


if __name__ == "__main__":
    main()
