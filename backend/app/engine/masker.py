"""
Core Masking Engine
Performs sensitive data detection and masking with parallel processing
Supports archive files (tgz, tar.gz, zip, etc.)
"""
import asyncio
import time
import uuid
import os
import tempfile
import shutil
from typing import List, Dict, Optional, Tuple, Callable
from dataclasses import dataclass, field
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from app.engine.rules import MaskingRule, get_enabled_rules
from app.engine.archive import (
    detect_archive_type, extract_archive, create_archive,
    get_text_files, is_text_file, ArchiveType, get_archive_extension
)


@dataclass
class MatchInfo:
    """Information about a single match"""
    line_number: int
    original: str
    masked: str
    rule_id: str
    start_pos: int
    end_pos: int


@dataclass
class RuleStats:
    """Statistics for a single rule"""
    rule_id: str
    rule_name: str
    matches: int = 0
    examples: List[Dict] = field(default_factory=list)
    
    def add_match(self, match_info: MatchInfo, max_examples: int = 3):
        self.matches += 1
        if len(self.examples) < max_examples:
            self.examples.append({
                "line": match_info.line_number,
                "original": match_info.original,
                "masked": match_info.masked
            })


@dataclass
class MaskResult:
    """Result of masking operation"""
    masked_content: str
    total_matches: int
    total_lines: int
    processing_time_ms: float
    risk_score: int
    risk_level: str
    breakdown: List[RuleStats]
    whitelist_skipped: int = 0
    is_archive: bool = False
    archive_type: Optional[str] = None
    files_processed: int = 1
    masked_file_path: Optional[str] = None  # For archives, path to the masked archive


class MaskingEngine:
    """
    High-performance masking engine with parallel processing support
    """
    
    def __init__(self, max_workers: int = 16, chunk_size: int = 5000):
        self.max_workers = max_workers
        self.chunk_size = chunk_size  # Lines per chunk for parallel processing
        self.executor = ThreadPoolExecutor(max_workers=max_workers)
    
    async def mask_content(
        self,
        content: str,
        rules: Optional[List[MaskingRule]] = None,
        whitelist: Optional[List[str]] = None,
        progress_callback: Optional[Callable] = None
    ) -> MaskResult:
        """
        Mask sensitive content with parallel processing for large files
        """
        start_time = time.perf_counter()
        
        if rules is None:
            rules = get_enabled_rules()
        
        if whitelist is None:
            whitelist = []

        # Initialize stats for each rule
        stats_map: Dict[str, RuleStats] = {
            rule.id: RuleStats(
                rule_id=rule.id,
                rule_name=rule.name
            )
            for rule in rules
        }

        # ── Full-content pre-pass for multiline (DOTALL) rules ──────────────
        # Line-by-line processing cannot match patterns that span multiple lines
        # (e.g. SSH/PGP private key blocks). Rules with re.DOTALL are applied
        # against the full content first, then removed from the line-by-line pass.
        import re as _re
        all_rules = rules  # keep reference for risk scoring
        multiline_rules = [r for r in rules if r.pattern.flags & _re.DOTALL]
        line_rules = [r for r in rules if not (r.pattern.flags & _re.DOTALL)]
        all_multiline_matches: List[MatchInfo] = []

        for rule in multiline_rules:
            # Capture rule and running content snapshot for correct line numbers
            def _make_replacer(_rule, _matches, _whitelist):
                def _replacer(match):
                    original = match.group(0)
                    is_whitelisted = any(w.lower() in original.lower() for w in _whitelist)
                    # Line number is relative to content *before* this substitution
                    line_number = match.string[:match.start()].count('\n') + 1
                    if is_whitelisted:
                        _matches.append(MatchInfo(
                            line_number=line_number, original=original,
                            masked=original, rule_id="__whitelist__",
                            start_pos=match.start(), end_pos=match.end()
                        ))
                        return original
                    masked = _rule.mask(original)
                    _matches.append(MatchInfo(
                        line_number=line_number, original=original,
                        masked=masked, rule_id=_rule.id,
                        start_pos=match.start(), end_pos=match.end()
                    ))
                    return masked
                return _replacer

            content = rule.pattern.sub(
                _make_replacer(rule, all_multiline_matches, whitelist),
                content
            )

        lines = content.split('\n')
        total_lines = len(lines)

        # Use only non-DOTALL rules for the line-by-line phase
        rules = line_rules

        # Decide processing mode based on file size
        if total_lines > self.chunk_size:
            # Parallel processing for large files
            masked_lines, all_matches = await self._parallel_mask(
                lines, rules, whitelist, progress_callback
            )
        else:
            # Single-threaded for small files
            masked_lines, all_matches = self._mask_lines(
                lines, rules, whitelist, 0
            )
            if progress_callback:
                progress_callback(100)
        
        # Aggregate statistics (include pre-pass multiline matches)
        all_matches = all_multiline_matches + list(all_matches)
        total_matches = 0
        whitelist_skipped = 0
        
        for match_info in all_matches:
            if match_info.rule_id == "__whitelist__":
                whitelist_skipped += 1
            else:
                total_matches += 1
                stats_map[match_info.rule_id].add_match(match_info)
        
        # Calculate risk score — use all_rules (includes DOTALL rules) so that
        # multiline matches contribute their weight to the score correctly.
        risk_score = self._calculate_risk_score(stats_map, all_rules, total_lines)
        risk_level = self._get_risk_level(risk_score)
        
        processing_time_ms = max((time.perf_counter() - start_time) * 1000, 0.01)

        # Track which rules actually fired — bump use_count asynchronously
        matched_rule_ids = [s.rule_id for s in stats_map.values() if s.matches > 0]
        if matched_rule_ids:
            try:
                from app.engine.rule_service import rule_service as _rs
                _rs.increment_use_count(matched_rule_ids)
            except Exception:
                pass  # Never fail a mask job due to stats tracking
        
        return MaskResult(
            masked_content='\n'.join(masked_lines),
            total_matches=total_matches,
            total_lines=total_lines,
            processing_time_ms=round(processing_time_ms, 2),
            risk_score=risk_score,
            risk_level=risk_level,
            breakdown=[stats for stats in stats_map.values() if stats.matches > 0],
            whitelist_skipped=whitelist_skipped
        )
    
    async def _parallel_mask(
        self,
        lines: List[str],
        rules: List[MaskingRule],
        whitelist: List[str],
        progress_callback: Optional[Callable]
    ) -> Tuple[List[str], List[MatchInfo]]:
        """Process large files in parallel chunks"""
        loop = asyncio.get_event_loop()
        
        # Split into chunks
        chunks = []
        for i in range(0, len(lines), self.chunk_size):
            chunk = lines[i:i + self.chunk_size]
            start_line = i
            chunks.append((chunk, start_line))
        
        total_chunks = len(chunks)
        completed_chunks = 0
        
        # Process chunks in parallel
        async def process_chunk(chunk_data):
            nonlocal completed_chunks
            chunk_lines, start_line = chunk_data
            result = await loop.run_in_executor(
                self.executor,
                self._mask_lines,
                chunk_lines,
                rules,
                whitelist,
                start_line
            )
            completed_chunks += 1
            if progress_callback:
                progress = int((completed_chunks / total_chunks) * 100)
                progress_callback(progress)
            return result
        
        # Execute all chunks concurrently
        results = await asyncio.gather(*[process_chunk(c) for c in chunks])
        
        # Merge results
        all_masked_lines = []
        all_matches = []
        
        for masked_lines, matches in results:
            all_masked_lines.extend(masked_lines)
            all_matches.extend(matches)
        
        return all_masked_lines, all_matches
    
    def _mask_lines(
        self,
        lines: List[str],
        rules: List[MaskingRule],
        whitelist: List[str],
        start_line: int
    ) -> Tuple[List[str], List[MatchInfo]]:
        """Mask a list of lines (single-threaded)"""
        masked_lines = []
        all_matches = []
        
        for i, line in enumerate(lines):
            line_number = start_line + i + 1
            masked_line, matches = self._mask_single_line(
                line, rules, whitelist, line_number
            )
            masked_lines.append(masked_line)
            all_matches.extend(matches)
        
        return masked_lines, all_matches
    
    def _mask_single_line(
        self,
        line: str,
        rules: List[MaskingRule],
        whitelist: List[str],
        line_number: int
    ) -> Tuple[str, List[MatchInfo]]:
        """Mask sensitive data in a single line"""
        matches = []
        masked_line = line
        offset = 0
        
        # Collect all matches with positions
        all_rule_matches = []
        
        for rule in rules:
            for match in rule.pattern.finditer(line):
                original = match.group(0)
                
                # Check whitelist
                is_whitelisted = any(w.lower() in original.lower() for w in whitelist)
                
                if is_whitelisted:
                    matches.append(MatchInfo(
                        line_number=line_number,
                        original=original,
                        masked=original,
                        rule_id="__whitelist__",
                        start_pos=match.start(),
                        end_pos=match.end()
                    ))
                else:
                    all_rule_matches.append({
                        'rule': rule,
                        'match': match,
                        'original': original,
                        'start': match.start(),
                        'end': match.end()
                    })
        
        # Sort by position (reverse order for replacement)
        all_rule_matches.sort(key=lambda x: x['start'], reverse=True)
        
        # Apply replacements from end to start to preserve positions
        for m in all_rule_matches:
            rule = m['rule']
            original = m['original']
            masked = rule.mask(original)
            
            # Check for overlapping matches - skip if already masked
            start, end = m['start'], m['end']
            
            matches.append(MatchInfo(
                line_number=line_number,
                original=original,
                masked=masked,
                rule_id=rule.id,
                start_pos=start,
                end_pos=end
            ))
            
            masked_line = masked_line[:start] + masked + masked_line[end:]
        
        return masked_line, matches
    
    def _calculate_risk_score(
        self,
        stats_map: Dict[str, RuleStats],
        rules: List[MaskingRule],
        total_lines: int
    ) -> int:
        """Calculate risk score based on matches and weights"""
        if total_lines == 0:
            return 0
        
        weighted_sum = 0
        for rule in rules:
            stats = stats_map.get(rule.id)
            if stats:
                weighted_sum += stats.matches * rule.weight
        
        # Normalize to 0-100 scale
        # More matches per line = higher risk
        score = min(100, int((weighted_sum / total_lines) * 50))
        return score
    
    def _get_risk_level(self, score: int) -> str:
        """Get risk level from score"""
        if score < 30:
            return "LOW"
        elif score < 60:
            return "MEDIUM"
        else:
            return "HIGH"
    
    async def mask_file(
        self,
        file_path: str,
        output_dir: str,
        rules: Optional[List[MaskingRule]] = None,
        whitelist: Optional[List[str]] = None,
        progress_callback: Optional[Callable] = None
    ) -> MaskResult:
        """
        Mask a file - supports both regular files and archives
        For archives: extracts, processes all text files, and repacks
        """
        start_time = time.time()
        
        if rules is None:
            rules = get_enabled_rules()
        
        if whitelist is None:
            whitelist = []
        
        filename = os.path.basename(file_path)
        archive_type = detect_archive_type(filename)
        
        if archive_type == ArchiveType.NONE:
            # Regular file - use existing content-based masking
            with open(file_path, 'r', encoding='utf-8', errors='replace') as f:
                content = f.read()
            
            result = await self.mask_content(content, rules, whitelist, progress_callback)
            
            # Write masked content to output
            output_path = os.path.join(output_dir, f"masked_{filename}")
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write(result.masked_content)
            
            result.masked_file_path = output_path
            return result
        
        # Archive file processing
        return await self._mask_archive(
            file_path, output_dir, archive_type, rules, whitelist, progress_callback
        )
    
    async def _mask_archive(
        self,
        archive_path: str,
        output_dir: str,
        archive_type: ArchiveType,
        rules: List[MaskingRule],
        whitelist: List[str],
        progress_callback: Optional[Callable]
    ) -> MaskResult:
        """Process an archive file"""
        import logging
        logger = logging.getLogger(__name__)
        
        start_time = time.time()
        temp_dir = None
        
        try:
            # Create temporary directory for extraction
            temp_dir = tempfile.mkdtemp(prefix="mask_archive_")
            extract_dir = os.path.join(temp_dir, "extracted")
            os.makedirs(extract_dir)
            
            # Extract archive
            logger.info(f"Extracting archive {archive_path} to {extract_dir}")
            _, extracted_files = extract_archive(archive_path, extract_dir)
            
            # Find all text files
            text_files = get_text_files(extract_dir)
            total_files = len(text_files)
            logger.info(f"Found {total_files} text files to process")
            
            # Initialize aggregated stats
            all_stats: Dict[str, RuleStats] = {
                rule.id: RuleStats(
                    rule_id=rule.id,
                    rule_name=rule.name
                )
                for rule in rules
            }
            
            total_matches = 0
            total_lines = 0
            whitelist_skipped = 0
            
            # Process each text file
            for idx, text_file in enumerate(text_files):
                try:
                    with open(text_file, 'r', encoding='utf-8', errors='replace') as f:
                        content = f.read()
                    
                    result = await self.mask_content(content, rules, whitelist)
                    
                    # Write masked content back
                    with open(text_file, 'w', encoding='utf-8') as f:
                        f.write(result.masked_content)
                    
                    # Aggregate stats
                    total_matches += result.total_matches
                    total_lines += result.total_lines
                    whitelist_skipped += result.whitelist_skipped
                    
                    rel_path = os.path.relpath(text_file, extract_dir)
                    
                    for breakdown in result.breakdown:
                        stats = all_stats[breakdown.rule_id]
                        stats.matches += breakdown.matches
                        # Keep up to 3 examples per rule, annotated with relative file path
                        for ex in breakdown.examples:
                            if len(stats.examples) < 3:
                                stats.examples.append({**ex, "file": rel_path})
                    
                except Exception as e:
                    logger.warning(f"Failed to process file {text_file}: {e}")
                    continue
                
                # Update progress
                if progress_callback:
                    progress = int(((idx + 1) / total_files) * 90)  # Reserve 10% for repacking
                    progress_callback(progress)
            
            # Create output archive
            filename = os.path.basename(archive_path)
            # Remove original extension and add masked_ prefix
            base_name = filename
            for ext in ['.tar.gz', '.tgz', '.tar.bz2', '.tbz2', '.tar.xz', '.txz', '.tar', '.zip']:
                if filename.lower().endswith(ext):
                    base_name = filename[:-len(ext)]
                    break
            
            output_filename = f"masked_{base_name}{get_archive_extension(archive_type)}"
            output_path = os.path.join(output_dir, output_filename)
            
            logger.info(f"Creating masked archive {output_path}")
            create_archive(extract_dir, output_path, archive_type)
            
            if progress_callback:
                progress_callback(100)
            
            # Calculate risk score
            risk_score = self._calculate_risk_score(all_stats, rules, total_lines) if total_lines > 0 else 0
            risk_level = self._get_risk_level(risk_score)
            
            processing_time_ms = (time.time() - start_time) * 1000
            
            # Track which rules actually fired — bump use_count
            matched_rule_ids = [s.rule_id for s in all_stats.values() if s.matches > 0]
            if matched_rule_ids:
                try:
                    from app.engine.rule_service import rule_service as _rs
                    _rs.increment_use_count(matched_rule_ids)
                except Exception:
                    pass

            return MaskResult(
                masked_content="",  # Archive content is in the file
                total_matches=total_matches,
                total_lines=total_lines,
                processing_time_ms=round(processing_time_ms, 2),
                risk_score=risk_score,
                risk_level=risk_level,
                breakdown=[stats for stats in all_stats.values() if stats.matches > 0],
                whitelist_skipped=whitelist_skipped,
                is_archive=True,
                archive_type=archive_type.value,
                files_processed=total_files,
                masked_file_path=output_path
            )
        
        finally:
            # Cleanup temp directory
            if temp_dir and os.path.exists(temp_dir):
                try:
                    shutil.rmtree(temp_dir)
                except Exception as e:
                    logger.warning(f"Failed to cleanup temp dir {temp_dir}: {e}")
    
    def shutdown(self):
        """Shutdown the executor"""
        self.executor.shutdown(wait=True)


# Global engine instance
_engine: Optional[MaskingEngine] = None


def get_engine() -> MaskingEngine:
    """Get or create the global masking engine"""
    global _engine
    if _engine is None:
        _engine = MaskingEngine(max_workers=16)
    return _engine
