"""
Archive Handler
Supports extracting and repacking various archive formats
"""
import os
import tarfile
import zipfile
import tempfile
import shutil
from pathlib import Path
from typing import List, Tuple, Optional
from dataclasses import dataclass
from enum import Enum
import logging

logger = logging.getLogger(__name__)

# Maximum total decompressed size (2 GB) to prevent zip bombs
MAX_EXTRACT_SIZE = 2 * 1024 * 1024 * 1024


class ArchiveType(Enum):
    """Supported archive types"""
    TAR_GZ = "tar.gz"
    TGZ = "tgz"
    TAR_BZ2 = "tar.bz2"
    TAR_XZ = "tar.xz"
    TAR = "tar"
    ZIP = "zip"
    NONE = "none"  # Not an archive


@dataclass
class ArchiveInfo:
    """Information about an archive"""
    archive_type: ArchiveType
    original_name: str
    extract_dir: str
    file_count: int
    total_size: int


# Text file extensions that should be processed
TEXT_EXTENSIONS = {
    '.txt', '.log', '.conf', '.cfg', '.ini', '.yaml', '.yml', '.json',
    '.xml', '.html', '.htm', '.css', '.js', '.ts', '.py', '.sh', '.bash',
    '.zsh', '.fish', '.pl', '.rb', '.php', '.java', '.c', '.cpp', '.h',
    '.hpp', '.go', '.rs', '.md', '.rst', '.csv', '.tsv', '.sql', '.env',
    '.properties', '.toml', '.spec', '.service', '.socket', '.timer',
    '.mount', '.target', '.path', '.slice', '.scope', '.swap',
    # No extension files that are typically text
}

# Files without extension that should be processed
TEXT_FILENAMES = {
    'Dockerfile', 'Makefile', 'Jenkinsfile', 'Vagrantfile', 'Gemfile',
    'Rakefile', 'Procfile', 'LICENSE', 'README', 'CHANGELOG', 'AUTHORS',
    'CONTRIBUTORS', 'INSTALL', 'NEWS', 'TODO', 'COPYING', 'VERSION',
}


def detect_archive_type(filename: str) -> ArchiveType:
    """Detect archive type from filename"""
    lower_name = filename.lower()
    
    if lower_name.endswith('.tar.gz') or lower_name.endswith('.tgz'):
        return ArchiveType.TAR_GZ
    elif lower_name.endswith('.tar.bz2') or lower_name.endswith('.tbz2'):
        return ArchiveType.TAR_BZ2
    elif lower_name.endswith('.tar.xz') or lower_name.endswith('.txz'):
        return ArchiveType.TAR_XZ
    elif lower_name.endswith('.tar'):
        return ArchiveType.TAR
    elif lower_name.endswith('.zip'):
        return ArchiveType.ZIP
    else:
        return ArchiveType.NONE


def is_text_file(filepath: str) -> bool:
    """Check if a file is likely a text file"""
    path = Path(filepath)
    
    # Check by filename
    if path.name in TEXT_FILENAMES:
        return True
    
    # Check by extension
    suffix = path.suffix.lower()
    if suffix in TEXT_EXTENSIONS:
        return True
    
    # For files without extension, try to detect
    if not suffix:
        try:
            with open(filepath, 'rb') as f:
                chunk = f.read(8192)
                # Check for null bytes (binary indicator)
                if b'\x00' in chunk:
                    return False
                # Try to decode as UTF-8
                try:
                    chunk.decode('utf-8')
                    return True
                except UnicodeDecodeError:
                    return False
        except Exception:
            return False
    
    return False


def _check_zip_traversal(zf: zipfile.ZipFile, extract_to: str):
    """Reject ZIP files with path traversal entries (e.g. ../../etc/passwd)"""
    abs_target = os.path.realpath(extract_to)
    for member in zf.namelist():
        member_path = os.path.realpath(os.path.join(extract_to, member))
        if not member_path.startswith(abs_target + os.sep) and member_path != abs_target:
            raise ValueError(f"ZIP path traversal detected: {member}")


def _check_zip_bomb(zf: zipfile.ZipFile):
    """Reject ZIP files whose total decompressed size exceeds MAX_EXTRACT_SIZE"""
    total = sum(info.file_size for info in zf.infolist())
    if total > MAX_EXTRACT_SIZE:
        raise ValueError(
            f"ZIP bomb detected: decompressed size {total:,} bytes exceeds "
            f"limit of {MAX_EXTRACT_SIZE:,} bytes"
        )


def _check_tar_bomb(tar: tarfile.TarFile):
    """Reject tar files whose total decompressed size exceeds MAX_EXTRACT_SIZE"""
    total = sum(m.size for m in tar.getmembers() if m.isfile())
    if total > MAX_EXTRACT_SIZE:
        raise ValueError(
            f"Tar bomb detected: decompressed size {total:,} bytes exceeds "
            f"limit of {MAX_EXTRACT_SIZE:,} bytes"
        )


def extract_archive(archive_path: str, extract_to: str) -> Tuple[ArchiveType, List[str]]:
    """
    Extract an archive to a directory
    Returns: (archive_type, list of extracted file paths)
    """
    archive_type = detect_archive_type(archive_path)
    extracted_files = []
    
    if archive_type == ArchiveType.NONE:
        # Not an archive, just copy the file
        dest_path = os.path.join(extract_to, os.path.basename(archive_path))
        shutil.copy2(archive_path, dest_path)
        return archive_type, [dest_path]
    
    try:
        if archive_type in (ArchiveType.TAR_GZ, ArchiveType.TGZ):
            with tarfile.open(archive_path, 'r:gz') as tar:
                _check_tar_bomb(tar)
                tar.extractall(extract_to, filter='data')
                extracted_files = [os.path.join(extract_to, m.name) for m in tar.getmembers() if m.isfile()]
        
        elif archive_type == ArchiveType.TAR_BZ2:
            with tarfile.open(archive_path, 'r:bz2') as tar:
                _check_tar_bomb(tar)
                tar.extractall(extract_to, filter='data')
                extracted_files = [os.path.join(extract_to, m.name) for m in tar.getmembers() if m.isfile()]
        
        elif archive_type == ArchiveType.TAR_XZ:
            with tarfile.open(archive_path, 'r:xz') as tar:
                _check_tar_bomb(tar)
                tar.extractall(extract_to, filter='data')
                extracted_files = [os.path.join(extract_to, m.name) for m in tar.getmembers() if m.isfile()]
        
        elif archive_type == ArchiveType.TAR:
            with tarfile.open(archive_path, 'r:') as tar:
                _check_tar_bomb(tar)
                tar.extractall(extract_to, filter='data')
                extracted_files = [os.path.join(extract_to, m.name) for m in tar.getmembers() if m.isfile()]
        
        elif archive_type == ArchiveType.ZIP:
            with zipfile.ZipFile(archive_path, 'r') as zf:
                _check_zip_traversal(zf, extract_to)
                _check_zip_bomb(zf)
                zf.extractall(extract_to)
                extracted_files = [os.path.join(extract_to, name) for name in zf.namelist() 
                                   if not name.endswith('/')]
        
        logger.info(f"Extracted {len(extracted_files)} files from {archive_path}")
        return archive_type, extracted_files
    
    except Exception as e:
        logger.error(f"Failed to extract archive {archive_path}: {e}")
        raise


def create_archive(source_dir: str, output_path: str, archive_type: ArchiveType) -> str:
    """
    Create an archive from a directory
    Returns: path to the created archive
    """
    try:
        if archive_type in (ArchiveType.TAR_GZ, ArchiveType.TGZ):
            with tarfile.open(output_path, 'w:gz') as tar:
                for root, dirs, files in os.walk(source_dir):
                    for file in files:
                        file_path = os.path.join(root, file)
                        arcname = os.path.relpath(file_path, source_dir)
                        tar.add(file_path, arcname=arcname)
        
        elif archive_type == ArchiveType.TAR_BZ2:
            with tarfile.open(output_path, 'w:bz2') as tar:
                for root, dirs, files in os.walk(source_dir):
                    for file in files:
                        file_path = os.path.join(root, file)
                        arcname = os.path.relpath(file_path, source_dir)
                        tar.add(file_path, arcname=arcname)
        
        elif archive_type == ArchiveType.TAR_XZ:
            with tarfile.open(output_path, 'w:xz') as tar:
                for root, dirs, files in os.walk(source_dir):
                    for file in files:
                        file_path = os.path.join(root, file)
                        arcname = os.path.relpath(file_path, source_dir)
                        tar.add(file_path, arcname=arcname)
        
        elif archive_type == ArchiveType.TAR:
            with tarfile.open(output_path, 'w:') as tar:
                for root, dirs, files in os.walk(source_dir):
                    for file in files:
                        file_path = os.path.join(root, file)
                        arcname = os.path.relpath(file_path, source_dir)
                        tar.add(file_path, arcname=arcname)
        
        elif archive_type == ArchiveType.ZIP:
            with zipfile.ZipFile(output_path, 'w', zipfile.ZIP_DEFLATED) as zf:
                for root, dirs, files in os.walk(source_dir):
                    for file in files:
                        file_path = os.path.join(root, file)
                        arcname = os.path.relpath(file_path, source_dir)
                        zf.write(file_path, arcname=arcname)
        
        logger.info(f"Created archive {output_path}")
        return output_path
    
    except Exception as e:
        logger.error(f"Failed to create archive {output_path}: {e}")
        raise


def get_text_files(directory: str) -> List[str]:
    """Get all text files in a directory recursively"""
    text_files = []
    
    for root, dirs, files in os.walk(directory):
        # Skip hidden directories
        dirs[:] = [d for d in dirs if not d.startswith('.')]
        
        for file in files:
            if file.startswith('.'):
                continue
            
            file_path = os.path.join(root, file)
            if is_text_file(file_path):
                text_files.append(file_path)
    
    return text_files


def get_archive_extension(archive_type: ArchiveType) -> str:
    """Get the file extension for an archive type"""
    extensions = {
        ArchiveType.TAR_GZ: '.tar.gz',
        ArchiveType.TGZ: '.tgz',
        ArchiveType.TAR_BZ2: '.tar.bz2',
        ArchiveType.TAR_XZ: '.tar.xz',
        ArchiveType.TAR: '.tar',
        ArchiveType.ZIP: '.zip',
        ArchiveType.NONE: '',
    }
    return extensions.get(archive_type, '')
