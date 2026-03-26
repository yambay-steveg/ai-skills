#!/usr/bin/env python3
"""Template skill script.

Replace this with your skill's logic. This script is called by Claude
via the instructions in SKILL.md.
"""
import argparse
import sys


def main():
    parser = argparse.ArgumentParser(description="Template skill")
    parser.add_argument("--arg", required=True, help="Example argument")
    args = parser.parse_args()

    # Your skill logic here
    print(f"Running with: {args.arg}")


if __name__ == "__main__":
    main()
