#!/usr/bin/env python3
"""Extend database with new tables for AI metadata"""
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from database import extend_database

if __name__ == "__main__":
    print("Extending database schema...")
    extend_database("data/uploader.db")
    print("✅ Done!")
