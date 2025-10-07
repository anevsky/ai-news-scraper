"""
Pytest configuration file.
Loads environment variables before running tests.
"""

import os
from pathlib import Path
from dotenv import load_dotenv


def pytest_configure(config):
    """Load environment variables from .env file before tests run."""
    # Load .env file from project root
    env_path = Path(__file__).parent / '.env'
    if env_path.exists():
        load_dotenv(env_path)
        print(f"\n✓ Loaded environment variables from {env_path}")

        # Verify API keys are loaded (without printing the actual keys)
        if os.getenv("OPENAI_API_KEY"):
            print("✓ OPENAI_API_KEY loaded")
        else:
            print("⚠ OPENAI_API_KEY not found in .env")

        if os.getenv("ANTHROPIC_API_KEY"):
            print("✓ ANTHROPIC_API_KEY loaded")
        else:
            print("⚠ ANTHROPIC_API_KEY not found in .env")
    else:
        print(f"\n⚠ No .env file found at {env_path}")
        print("  Some tests may be skipped")
