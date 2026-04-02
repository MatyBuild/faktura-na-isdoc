"""
Nastaví prostředí před importem modulů, které vyžadují env proměnné.
"""
import os
os.environ.setdefault("ANTHROPIC_API_KEY", "sk-ant-test-dummy")
