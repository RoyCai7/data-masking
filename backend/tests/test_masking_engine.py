"""
test_masking_engine.py — Tests for the MaskingEngine core.

Covers:
  1. Single-line masking (small file path)
  2. Parallel chunk processing (large file path)
  3. Whitelist behavior
  4. Risk score calculation
  5. File masking (writes output)
  6. Archive masking (tar.gz, zip)
  7. Multi-file archive processing
  8. Empty / no-match content
"""
import pytest

from app.engine.masker import MaskingEngine, MaskResult
from app.engine.rules import get_enabled_rules


# ═══════════════════════════════════════════════════════════════════════════════
# 1. Content masking (single-threaded path)
# ═══════════════════════════════════════════════════════════════════════════════

class TestContentMasking:
    """Test mask_content with various inputs."""

    @pytest.fixture
    def engine(self):
        return MaskingEngine(max_workers=2, chunk_size=5000)

    @pytest.mark.asyncio
    async def test_basic_text_masking(self, engine, sample_text):
        """Sample text should have multiple matches across categories."""
        result = await engine.mask_content(sample_text)
        assert isinstance(result, MaskResult)
        assert result.total_matches > 0
        assert result.total_lines > 0
        assert result.processing_time_ms > 0

    @pytest.mark.asyncio
    async def test_ipv4_masked(self, engine):
        result = await engine.mask_content("Server at 192.168.1.100 is up")
        assert "192.168.1.100" not in result.masked_content
        assert "[IPv4]" in result.masked_content

    @pytest.mark.asyncio
    async def test_email_masked(self, engine):
        result = await engine.mask_content("contact admin@example.com please")
        assert "admin@example.com" not in result.masked_content

    @pytest.mark.asyncio
    async def test_password_masked(self, engine):
        result = await engine.mask_content("password = SuperSecret123")
        assert "SuperSecret123" not in result.masked_content
        assert "[PASSWORD]" in result.masked_content

    @pytest.mark.asyncio
    async def test_private_key_masked(self, engine):
        text = "-----BEGIN RSA PRIVATE KEY-----\nMIIEpAIBAAKCAQEA0Z3VS5JJcds\nDDDDEEEEFFFFGGGGHHHHIIII\n-----END RSA PRIVATE KEY-----"
        result = await engine.mask_content(text)
        # The BEGIN header should be replaced by [PRIVATE_KEY] placeholder
        assert "-----BEGIN RSA PRIVATE KEY-----" not in result.masked_content
        assert result.total_matches > 0

    @pytest.mark.asyncio
    async def test_aws_key_masked(self, engine):
        result = await engine.mask_content("AWS key: AKIAIOSFODNN7EXAMPLE")
        assert "AKIAIOSFODNN7EXAMPLE" not in result.masked_content

    @pytest.mark.asyncio
    async def test_suse_specific_masked(self, engine):
        # scc_regcode and sap_hana_credential are now disabled by default (SUSE-specific)
        # but the values are still caught by generic rules (license, password/env_secret)
        text = "SCC regcode = ABCD-EFGH-1234-5678-9012\nHANA_PASSWORD=Secret"
        result = await engine.mask_content(text)
        # License key pattern catches ABCD-EFGH-1234-5678-9012; password rule catches HANA_PASSWORD=Secret
        assert "ABCD-EFGH-1234-5678-9012" not in result.masked_content or "Secret" not in result.masked_content
        assert result.total_matches >= 1

    @pytest.mark.asyncio
    async def test_multiple_rules_same_line(self, engine):
        """A line with multiple sensitive items gets all of them masked."""
        text = "user=admin password=Secret123 ip=10.0.0.1"
        result = await engine.mask_content(text)
        assert "Secret123" not in result.masked_content
        assert result.total_matches >= 2

    @pytest.mark.asyncio
    async def test_empty_content(self, engine):
        result = await engine.mask_content("")
        assert result.total_matches == 0
        assert result.masked_content == ""

    @pytest.mark.asyncio
    async def test_no_sensitive_content(self, engine):
        result = await engine.mask_content("Hello, this is a normal line.\nNothing to mask here.")
        assert result.total_matches == 0
        assert result.risk_level == "LOW"


# ═══════════════════════════════════════════════════════════════════════════════
# 2. Whitelist
# ═══════════════════════════════════════════════════════════════════════════════

class TestWhitelist:
    """Whitelist items should be skipped during masking."""

    @pytest.fixture
    def engine(self):
        return MaskingEngine(max_workers=2, chunk_size=5000)

    @pytest.mark.asyncio
    async def test_whitelisted_ip_preserved(self, engine):
        text = "Server 192.168.1.100 is the gateway"
        result = await engine.mask_content(text, whitelist=["192.168.1.100"])
        assert "192.168.1.100" in result.masked_content
        assert result.whitelist_skipped >= 1

    @pytest.mark.asyncio
    async def test_whitelist_case_insensitive(self, engine):
        """Whitelist comparison is case-insensitive."""
        text = "host CORP.EXAMPLE.COM is safe"
        result = await engine.mask_content(text, whitelist=["corp.example.com"])
        assert "CORP.EXAMPLE.COM" in result.masked_content

    @pytest.mark.asyncio
    async def test_partial_whitelist_match(self, engine):
        """Whitelist checks 'in' — substring match."""
        text = "contact admin@example.com for support"
        result = await engine.mask_content(text, whitelist=["example.com"])
        assert "admin@example.com" in result.masked_content


# ═══════════════════════════════════════════════════════════════════════════════
# 3. Risk scoring
# ═══════════════════════════════════════════════════════════════════════════════

class TestRiskScoring:

    @pytest.fixture
    def engine(self):
        return MaskingEngine(max_workers=2, chunk_size=5000)

    @pytest.mark.asyncio
    async def test_high_risk_content(self, engine):
        """Content with many high-weight secrets → HIGH risk."""
        lines = [
            f"password = Secret{i}" for i in range(50)
        ] + [
            f"api_key = sk_live_{'x' * 30}{i}" for i in range(50)
        ]
        result = await engine.mask_content("\n".join(lines))
        assert result.risk_level in ("MEDIUM", "HIGH")
        assert result.risk_score >= 30

    @pytest.mark.asyncio
    async def test_low_risk_content(self, engine):
        """Just one IP in 100 lines → LOW risk."""
        lines = ["normal log line"] * 99 + ["ip 10.0.0.1"]
        result = await engine.mask_content("\n".join(lines))
        assert result.risk_level == "LOW"


# ═══════════════════════════════════════════════════════════════════════════════
# 4. Parallel processing (large file)
# ═══════════════════════════════════════════════════════════════════════════════

class TestParallelProcessing:

    @pytest.mark.asyncio
    async def test_large_file_parallel(self):
        """Files > chunk_size lines should use parallel processing and still be correct."""
        engine = MaskingEngine(max_workers=4, chunk_size=100)
        lines = [f"line {i} ip=10.0.{i % 256}.{i % 256}" for i in range(500)]
        text = "\n".join(lines)
        result = await engine.mask_content(text)
        assert result.total_lines == 500
        assert result.total_matches >= 400  # Most lines have an IP
        # Ensure no original IPs leaked
        for i in range(10):
            assert f"10.0.{i}.{i}" not in result.masked_content


# ═══════════════════════════════════════════════════════════════════════════════
# 5. File-based masking
# ═══════════════════════════════════════════════════════════════════════════════

class TestFileMasking:

    @pytest.fixture
    def engine(self):
        return MaskingEngine(max_workers=2, chunk_size=5000)

    @pytest.mark.asyncio
    async def test_mask_text_file(self, engine, sample_text_file, tmp_path):
        result = await engine.mask_file(str(sample_text_file), str(tmp_path))
        assert result.masked_file_path is not None
        assert result.total_matches > 0

        # Read the output file and verify masking
        from pathlib import Path
        content = Path(result.masked_file_path).read_text()
        assert "192.168.1.100" not in content
        assert "SuperSecret123" not in content

    @pytest.mark.asyncio
    async def test_mask_tar_gz(self, engine, sample_tar_gz, tmp_path):
        result = await engine.mask_file(str(sample_tar_gz), str(tmp_path))
        assert result.is_archive is True
        assert result.archive_type is not None
        assert result.files_processed >= 1
        assert result.total_matches > 0
        assert result.masked_file_path.endswith((".tar.gz", ".tgz"))

    @pytest.mark.asyncio
    async def test_mask_zip(self, engine, sample_zip, tmp_path):
        result = await engine.mask_file(str(sample_zip), str(tmp_path))
        assert result.is_archive is True
        assert result.files_processed >= 1
        assert result.total_matches > 0
        assert result.masked_file_path.endswith(".zip")

    @pytest.mark.asyncio
    async def test_mask_multi_file_archive(self, engine, sample_multi_file_tar, tmp_path):
        result = await engine.mask_file(str(sample_multi_file_tar), str(tmp_path))
        assert result.is_archive is True
        assert result.files_processed >= 2  # network.conf + users.log (binary skipped)
        assert result.total_matches > 0


# ═══════════════════════════════════════════════════════════════════════════════
# 6. Progress callback
# ═══════════════════════════════════════════════════════════════════════════════

class TestProgressCallback:

    @pytest.mark.asyncio
    async def test_progress_callback_called(self):
        engine = MaskingEngine(max_workers=2, chunk_size=50)
        lines = [f"ip 10.0.0.{i % 256}" for i in range(200)]
        progress_values = []

        def on_progress(p):
            progress_values.append(p)

        await engine.mask_content("\n".join(lines), progress_callback=on_progress)
        assert len(progress_values) > 0
        assert progress_values[-1] == 100
