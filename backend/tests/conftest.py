"""
conftest.py — Shared fixtures for the entire test suite.

Key design:
  • Every test gets a fresh, isolated SQLite database (tmp_path)
  • AUTH_ENABLED is forced OFF so API tests don't need keys
  • A pre-configured AsyncClient talks to the real FastAPI app
  • Sample files (text, archive) are generated once per session
"""
import os
import sys
import asyncio
import tempfile
import tarfile
import zipfile
from pathlib import Path

import pytest
import pytest_asyncio

# ── ensure `app` is importable ──────────────────────────────────────────────
BACKEND_DIR = Path(__file__).resolve().parent.parent          # backend/
sys.path.insert(0, str(BACKEND_DIR))

# ── force auth OFF for all tests ────────────────────────────────────────────
os.environ["AUTH_ENABLED"] = "false"


# ── fresh DB per test ───────────────────────────────────────────────────────
@pytest.fixture(autouse=True)
def _isolate_db(tmp_path):
    """
    Give each test its own blank rules.db.
    Patches the DB_PATH in repository and re-inits the service.
    """
    import threading
    db_file = str(tmp_path / "rules.db")
    os.environ["RULES_DB_PATH"] = db_file

    import app.engine.repository as repo
    repo.DB_PATH = Path(db_file)
    # Force new thread-local connections for this test
    repo._local = threading.local()

    from app.engine.rule_service import rule_service
    # Reset the singleton so initialize() runs afresh
    rule_service._cache = []
    rule_service._cache_map = {}
    rule_service._initialized = False
    rule_service.initialize()

    yield

    # Cleanup
    rule_service._cache = []
    rule_service._cache_map = {}
    rule_service._initialized = False


# ── FastAPI test client ─────────────────────────────────────────────────────
@pytest_asyncio.fixture
async def client():
    """Async HTTP client talking to the real app (no network)."""
    from httpx import AsyncClient, ASGITransport
    from app.main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


# ── sample text content with sensitive data ─────────────────────────────────
SAMPLE_TEXT = """\
# System Configuration
server_ip = 192.168.1.100
gateway   = 10.0.0.1/24
mac_addr  = AA:BB:CC:DD:EE:FF

user = admin
email = john.doe@example.com
phone = +86-138-0013-8000

password = SuperSecret123!
api_key  = sk_live_4eC39HqLyjWDarjtT1zdp7dc
aws_key  = AKIAIOSFODNN7EXAMPLE
bearer   = Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.payload.signature

HANA_PASSWORD = SapSecret789
SID = PRD
Serial Number: ABC123XYZ789
UUID: 550e8400-e29b-41d4-a716-446655440000

LDAP DN: CN=admin,OU=Users,DC=corp,DC=example,DC=com
AccountKey=Eby8vdM02xNOcqFlqUwJPLlmEtlCDXJ1OUzFT50uSRZ6IFsuFq2UVErCz4I6tq==

-----BEGIN RSA PRIVATE KEY-----
MIIEpAIBAAKCAQEA0Z3VS5JJcds3xfnAAAABBBBCCCC
DDDDEEEEFFFFGGGGHHHHIIIIJJJJKKKKLLLL
-----END RSA PRIVATE KEY-----
"""


@pytest.fixture
def sample_text():
    return SAMPLE_TEXT


@pytest.fixture
def sample_text_file(tmp_path):
    """Write sample text to a .log file and return its path."""
    p = tmp_path / "supportconfig.log"
    p.write_text(SAMPLE_TEXT, encoding="utf-8")
    return p


@pytest.fixture
def sample_tar_gz(tmp_path, sample_text_file):
    """Create a .tar.gz archive containing the sample text file."""
    archive_path = tmp_path / "bundle.tar.gz"
    with tarfile.open(str(archive_path), "w:gz") as tar:
        tar.add(str(sample_text_file), arcname="supportconfig.log")
    return archive_path


@pytest.fixture
def sample_zip(tmp_path, sample_text_file):
    """Create a .zip archive containing the sample text file."""
    archive_path = tmp_path / "bundle.zip"
    with zipfile.ZipFile(str(archive_path), "w", zipfile.ZIP_DEFLATED) as zf:
        zf.write(str(sample_text_file), arcname="supportconfig.log")
    return archive_path


@pytest.fixture
def sample_multi_file_tar(tmp_path):
    """Create a .tgz with multiple files: config, log, binary."""
    d = tmp_path / "multi"
    d.mkdir()

    (d / "network.conf").write_text(
        "ip=10.20.30.40\ngateway=10.20.30.1\npassword=NetSecret\n"
    )
    (d / "users.log").write_text(
        "user john logged in\nemail: alice@corp.example.com\n"
    )
    # Binary file (should be skipped)
    (d / "secret.bin").write_bytes(os.urandom(256))

    archive_path = tmp_path / "multi.tgz"
    with tarfile.open(str(archive_path), "w:gz") as tar:
        for f in d.iterdir():
            tar.add(str(f), arcname=f.name)
    return archive_path
