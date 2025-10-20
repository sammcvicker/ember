"""Performance tests for Ember indexing and search operations.

These tests measure real-world performance characteristics to ensure
the system scales appropriately for typical codebases.
"""

import subprocess
import tempfile
import time
from pathlib import Path
from typing import NamedTuple

import pytest

from ember.adapters.fs.local import LocalFileSystem
from ember.adapters.fts.sqlite_fts import SQLiteFTS
from ember.adapters.git_cmd.git_adapter import GitAdapter
from ember.adapters.local_models.jina_embedder import JinaCodeEmbedder
from ember.adapters.parsers.line_chunker import LineChunker
from ember.adapters.parsers.tree_sitter_chunker import TreeSitterChunker
from ember.adapters.sqlite.chunk_repository import SQLiteChunkRepository
from ember.adapters.sqlite.file_repository import SQLiteFileRepository
from ember.adapters.sqlite.meta_repository import SQLiteMetaRepository
from ember.adapters.sqlite.schema import init_database
from ember.adapters.sqlite.vector_repository import SQLiteVectorRepository
from ember.adapters.vss.simple_vector_search import SimpleVectorSearch
from ember.core.chunking.chunk_usecase import ChunkFileUseCase
from ember.core.indexing.index_usecase import IndexingUseCase, IndexRequest
from ember.core.retrieval.search_usecase import SearchUseCase
from ember.domain.entities import Query


class PerformanceMetrics(NamedTuple):
    """Container for performance measurements."""

    operation: str
    duration_seconds: float
    file_count: int
    chunk_count: int
    memory_mb: float | None = None


class PerformanceTestFixture:
    """Test fixture for performance measurements."""

    def __init__(self, temp_dir: Path):
        self.temp_dir = temp_dir
        self.repo_path = temp_dir / "test_repo"
        self.ember_dir = self.repo_path / ".ember"
        self.db_path = self.ember_dir / "index.db"

        # Components will be initialized after setup_repo()
        self.vcs = None
        self.fs = None
        self.file_repo = None
        self.chunk_repo = None
        self.meta_repo = None
        self.vector_repo = None
        self.embedder = None
        self.tree_chunker = None
        self.line_chunker = None
        self.chunk_usecase = None
        self.index_usecase = None
        self.text_search = None
        self.vector_search = None
        self.search_usecase = None
        self.project_id = None

    def _init_components(self) -> None:
        """Initialize all components after repo is set up."""
        # Infrastructure adapters
        self.vcs = GitAdapter(self.repo_path)
        self.fs = LocalFileSystem()
        self.file_repo = SQLiteFileRepository(self.db_path)
        self.chunk_repo = SQLiteChunkRepository(self.db_path)
        self.meta_repo = SQLiteMetaRepository(self.db_path)
        self.vector_repo = SQLiteVectorRepository(self.db_path)
        self.embedder = JinaCodeEmbedder()

        # Chunking
        self.tree_chunker = TreeSitterChunker()
        self.line_chunker = LineChunker(window_size=120, stride=100)
        self.chunk_usecase = ChunkFileUseCase(
            tree_sitter_chunker=self.tree_chunker,
            line_chunker=self.line_chunker
        )

        # Project ID (hash of repo path)
        import hashlib
        self.project_id = hashlib.sha256(str(self.repo_path).encode()).hexdigest()[:16]

        # Indexing
        self.index_usecase = IndexingUseCase(
            vcs=self.vcs,
            fs=self.fs,
            chunk_usecase=self.chunk_usecase,
            embedder=self.embedder,
            chunk_repo=self.chunk_repo,
            vector_repo=self.vector_repo,
            file_repo=self.file_repo,
            meta_repo=self.meta_repo,
            project_id=self.project_id,
        )

        # Search
        self.text_search = SQLiteFTS(self.db_path)
        self.vector_search = SimpleVectorSearch(self.db_path)
        self.search_usecase = SearchUseCase(
            text_search=self.text_search,
            vector_search=self.vector_search,
            chunk_repo=self.chunk_repo,
            embedder=self.embedder,
        )

    def setup_repo(self) -> None:
        """Initialize the test repository."""
        self.repo_path.mkdir(parents=True)
        subprocess.run(["git", "init"], cwd=self.repo_path, check=True, capture_output=True)
        subprocess.run(
            ["git", "config", "user.email", "test@example.com"],
            cwd=self.repo_path,
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "Test User"],
            cwd=self.repo_path,
            check=True,
            capture_output=True,
        )

        # Initialize ember
        self.ember_dir.mkdir(parents=True)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        # Initialize database schema
        init_database(self.db_path)

        # Initialize all components now that repo is ready
        self._init_components()

    def create_synthetic_codebase(self, num_files: int, lines_per_file: int) -> None:
        """Create a synthetic Python codebase for testing.

        Args:
            num_files: Number of Python files to create
            lines_per_file: Approximate lines of code per file
        """
        for i in range(num_files):
            module_name = f"module_{i:04d}"
            file_path = self.repo_path / f"{module_name}.py"

            # Generate realistic Python code
            lines = [
                f'"""Module {module_name} - Auto-generated for testing."""',
                "",
                "from typing import List, Dict, Optional",
                "import json",
                "import logging",
                "",
                "logger = logging.getLogger(__name__)",
                "",
            ]

            # Add multiple classes and functions
            num_classes = max(1, lines_per_file // 50)
            for j in range(num_classes):
                class_name = f"Handler{j}"
                lines.extend([
                    f"class {class_name}:",
                    f'    """Handles processing for {class_name}."""',
                    "    ",
                    "    def __init__(self, config: Dict):",
                    "        self.config = config",
                    f"        self.name = '{class_name}'",
                    "        logger.info(f'Initialized {{self.name}}')",
                    "    ",
                    "    def process(self, data: List[str]) -> Dict:",
                    '        """Process input data and return results."""',
                    "        results = {}",
                    "        for item in data:",
                    "            key = item.strip()",
                    "            value = self._transform(key)",
                    "            results[key] = value",
                    "        return results",
                    "    ",
                    "    def _transform(self, value: str) -> str:",
                    '        """Internal transformation logic."""',
                    "        return value.upper().replace(' ', '_')",
                    "    ",
                ])

            # Add module-level functions
            lines.extend([
                f"def main_{module_name}():",
                '    """Entry point for this module."""',
                "    config = {'debug': True, 'timeout': 30}",
                "    handler = Handler0(config)",
                "    data = ['test', 'sample', 'data']",
                "    results = handler.process(data)",
                "    logger.info(f'Processed {{len(results)}} items')",
                "    return results",
                "",
                "if __name__ == '__main__':",
                f"    main_{module_name}()",
            ])

            file_path.write_text("\n".join(lines))

        # Create initial commit
        subprocess.run(["git", "add", "."], cwd=self.repo_path, check=True, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "Initial commit"],
            cwd=self.repo_path,
            check=True,
            capture_output=True,
        )

    def modify_files(self, num_files: int) -> None:
        """Modify a subset of files to test incremental indexing.

        Args:
            num_files: Number of files to modify
        """
        python_files = list(self.repo_path.glob("*.py"))[:num_files]

        for file_path in python_files:
            content = file_path.read_text()
            # Add a new function
            new_function = """
def new_helper_function(x: int) -> int:
    '''Newly added helper function.'''
    return x * 2 + 1
"""
            file_path.write_text(content + new_function)

        # Commit changes
        subprocess.run(["git", "add", "."], cwd=self.repo_path, check=True, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "Add helper functions"],
            cwd=self.repo_path,
            check=True,
            capture_output=True,
        )


@pytest.fixture
def perf_fixture():
    """Create a temporary performance test fixture."""
    with tempfile.TemporaryDirectory() as temp_dir:
        fixture = PerformanceTestFixture(Path(temp_dir))
        fixture.setup_repo()
        yield fixture


def test_initial_indexing_small(perf_fixture: PerformanceTestFixture):
    """Test initial indexing performance with a small codebase (~50 files)."""
    # Create a small codebase
    num_files = 50
    lines_per_file = 100
    perf_fixture.create_synthetic_codebase(num_files, lines_per_file)

    # Measure indexing time
    start = time.time()
    request = IndexRequest(repo_root=perf_fixture.repo_path, sync_mode="worktree")
    stats = perf_fixture.index_usecase.execute(request)
    duration = time.time() - start

    metrics = PerformanceMetrics(
        operation="initial_index_small",
        duration_seconds=duration,
        file_count=stats.files_indexed,
        chunk_count=stats.chunks_created,
    )

    print(f"\n{'='*60}")
    print("Small Codebase Initial Indexing")
    print(f"{'='*60}")
    print(f"Files indexed: {metrics.file_count}")
    print(f"Chunks created: {metrics.chunk_count}")
    print(f"Duration: {metrics.duration_seconds:.2f}s")
    print(f"Files/sec: {metrics.file_count / metrics.duration_seconds:.2f}")
    print(f"Chunks/sec: {metrics.chunk_count / metrics.duration_seconds:.2f}")
    print(f"{'='*60}\n")

    # Sanity checks (allow some tolerance for git-created files)
    assert stats.files_indexed >= num_files
    assert stats.files_indexed <= num_files + 5  # Allow for git-created files
    assert stats.chunks_created + stats.chunks_updated > num_files  # Should have chunks
    assert duration < 120  # Should complete in under 2 minutes for 50 files


def test_initial_indexing_medium(perf_fixture: PerformanceTestFixture):
    """Test initial indexing performance with a medium codebase (~200 files)."""
    num_files = 200
    lines_per_file = 150
    perf_fixture.create_synthetic_codebase(num_files, lines_per_file)

    start = time.time()
    request = IndexRequest(repo_root=perf_fixture.repo_path, sync_mode="worktree")
    stats = perf_fixture.index_usecase.execute(request)
    duration = time.time() - start

    metrics = PerformanceMetrics(
        operation="initial_index_medium",
        duration_seconds=duration,
        file_count=stats.files_indexed,
        chunk_count=stats.chunks_created,
    )

    print(f"\n{'='*60}")
    print("Medium Codebase Initial Indexing")
    print(f"{'='*60}")
    print(f"Files indexed: {metrics.file_count}")
    print(f"Chunks created: {metrics.chunk_count}")
    print(f"Duration: {metrics.duration_seconds:.2f}s")
    print(f"Files/sec: {metrics.file_count / metrics.duration_seconds:.2f}")
    print(f"Chunks/sec: {metrics.chunk_count / metrics.duration_seconds:.2f}")
    print(f"{'='*60}\n")

    assert stats.files_indexed >= num_files
    assert stats.files_indexed <= num_files + 5
    assert stats.chunks_created + stats.chunks_updated > num_files
    assert duration < 600  # Should complete in under 10 minutes for 200 files


def test_incremental_sync_performance(perf_fixture: PerformanceTestFixture):
    """Test incremental sync performance after modifying a subset of files."""
    # Create initial codebase
    num_files = 100
    perf_fixture.create_synthetic_codebase(num_files, 100)

    # Initial index
    request = IndexRequest(repo_root=perf_fixture.repo_path, sync_mode="worktree")
    initial_stats = perf_fixture.index_usecase.execute(request)

    # Modify 10% of files
    num_modified = 10
    perf_fixture.modify_files(num_modified)

    # Measure incremental sync
    start = time.time()
    request = IndexRequest(repo_root=perf_fixture.repo_path, sync_mode="worktree")
    sync_stats = perf_fixture.index_usecase.execute(request)
    duration = time.time() - start

    metrics = PerformanceMetrics(
        operation="incremental_sync",
        duration_seconds=duration,
        file_count=sync_stats.files_indexed,
        chunk_count=sync_stats.chunks_created,
    )

    print(f"\n{'='*60}")
    print("Incremental Sync Performance")
    print(f"{'='*60}")
    print(f"Total files: {num_files}")
    print(f"Modified files: {num_modified}")
    print(f"Files reindexed: {metrics.file_count}")
    print(f"Chunks updated: {metrics.chunk_count}")
    print(f"Duration: {metrics.duration_seconds:.2f}s")
    print(f"Speedup vs full reindex: {initial_stats.files_indexed / max(metrics.file_count, 1):.1f}x")
    print(f"{'='*60}\n")

    # Incremental should only process modified files (allow small tolerance)
    assert sync_stats.files_indexed <= num_modified + 2
    assert duration < 60  # Should be fast for small number of changes


def test_search_performance(perf_fixture: PerformanceTestFixture):
    """Test search query performance."""
    # Create and index a codebase
    num_files = 100
    perf_fixture.create_synthetic_codebase(num_files, 100)
    request = IndexRequest(repo_root=perf_fixture.repo_path, sync_mode="worktree")
    perf_fixture.index_usecase.execute(request)

    # Test queries
    queries = [
        "process data handler",
        "logging configuration",
        "transform value string",
        "initialize config",
        "main entry point",
    ]

    total_duration = 0.0
    for query_text in queries:
        start = time.time()
        query = Query(text=query_text, topk=10)
        results = perf_fixture.search_usecase.search(query)
        duration = time.time() - start
        total_duration += duration

        print(f"Query: '{query_text}' - {duration*1000:.1f}ms - {len(results)} results")

    avg_duration = total_duration / len(queries)

    print(f"\n{'='*60}")
    print("Search Performance")
    print(f"{'='*60}")
    print(f"Queries tested: {len(queries)}")
    print(f"Average query time: {avg_duration*1000:.1f}ms")
    print(f"Total time: {total_duration*1000:.1f}ms")
    print(f"{'='*60}\n")

    # Search should be fast
    assert avg_duration < 1.0  # Average query under 1 second


def test_database_size_scaling(perf_fixture: PerformanceTestFixture):
    """Test how database size scales with codebase size."""
    sizes_to_test = [10, 50, 100]
    results = []

    for num_files in sizes_to_test:
        # Clean start
        if perf_fixture.db_path.exists():
            perf_fixture.db_path.unlink()
        init_database(perf_fixture.db_path)

        # Remove old Python files
        for f in perf_fixture.repo_path.glob("*.py"):
            f.unlink()

        # Create codebase
        perf_fixture.create_synthetic_codebase(num_files, 100)
        request = IndexRequest(repo_root=perf_fixture.repo_path, sync_mode="worktree")
        stats = perf_fixture.index_usecase.execute(request)

        # Measure database size
        db_size_mb = perf_fixture.db_path.stat().st_size / (1024 * 1024)

        results.append({
            'files': num_files,
            'chunks': stats.chunks_created,
            'db_size_mb': db_size_mb,
            'mb_per_file': db_size_mb / num_files,
        })

        print(f"Files: {num_files:3d} | Chunks: {stats.chunks_created:4d} | "
              f"DB Size: {db_size_mb:6.2f}MB | Per File: {db_size_mb/num_files:.3f}MB")

    print(f"\n{'='*60}")
    print("Database Size Scaling")
    print(f"{'='*60}")
    for r in results:
        print(f"{r['files']:3d} files -> {r['db_size_mb']:6.2f}MB ({r['mb_per_file']:.3f}MB/file)")
    print(f"{'='*60}\n")

    # Database size should scale roughly linearly
    if len(results) >= 2:
        ratio = results[-1]['db_size_mb'] / results[0]['db_size_mb']
        file_ratio = results[-1]['files'] / results[0]['files']
        # Allow some overhead but should be roughly proportional
        assert ratio < file_ratio * 1.5


if __name__ == "__main__":
    """Run performance tests standalone."""
    import sys

    print("Running Ember Performance Tests")
    print("=" * 60)

    # Run with pytest
    sys.exit(pytest.main([__file__, "-v", "-s"]))
