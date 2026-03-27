"""Entry point for the Multi-Agent CLI system."""

import os
import sys
from dotenv import load_dotenv

# Load .env from project root
env_path = os.path.join(os.path.dirname(__file__), "..", ".env")
load_dotenv(env_path)


def main():
    from .tui import AgentCLI
    app = AgentCLI()
    app.run()


if __name__ == "__main__":
    main()
