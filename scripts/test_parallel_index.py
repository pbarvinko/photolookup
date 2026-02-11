#!/usr/bin/env python3
"""
Test script to verify parallel index building produces identical results to sequential.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

# Add parent dir to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from server.config import AppConfig
from server.index_store import IndexStore


def test_index_building():
    """Test that parallel and sequential builds produce identical hashes."""

    # Test configuration (small dataset)
    test_config = AppConfig(
        image_library_dirs=["tests/originals"] if Path("tests/originals").exists() else [],
        index_path="config/test_index.json",
        include_extensions=[".jpg", ".jpeg", ".png", ".tif", ".tiff"],
        build_workers=0,  # Auto (parallel)
    )

    if not test_config.image_library_dirs:
        print("❌ Test data directory not found. Skipping test.")
        print("   Expected: tests/originals/")
        return

    print("=" * 60)
    print("Testing Parallel vs Sequential Index Building")
    print("=" * 60)

    # Build with parallel processing
    print("\n1. Building index with PARALLEL processing...")
    parallel_config = AppConfig(
        image_library_dirs=test_config.image_library_dirs,
        index_path=test_config.index_path,
        include_extensions=test_config.include_extensions,
        build_workers=0,  # Auto-detect
    )

    store_parallel = IndexStore(parallel_config)
    start = time.time()
    data_parallel = store_parallel.build()
    parallel_time = time.time() - start

    parallel_items = data_parallel.items
    print(f"   ✓ Completed in {parallel_time:.2f}s")
    print(f"   ✓ Processed {len(parallel_items)} images")

    # Build with sequential processing
    print("\n2. Building index with SEQUENTIAL processing...")
    sequential_config = AppConfig(
        image_library_dirs=test_config.image_library_dirs,
        index_path=test_config.index_path,
        include_extensions=test_config.include_extensions,
        build_workers=1,  # Force sequential
    )

    store_sequential = IndexStore(sequential_config)
    start = time.time()
    data_sequential = store_sequential.build()
    sequential_time = time.time() - start

    sequential_items = data_sequential.items
    print(f"   ✓ Completed in {sequential_time:.2f}s")
    print(f"   ✓ Processed {len(sequential_items)} images")

    # Compare results
    print("\n3. Comparing results...")

    if len(parallel_items) != len(sequential_items):
        print("   ❌ FAILED: Different number of items")
        print(f"      Parallel: {len(parallel_items)}, Sequential: {len(sequential_items)}")
        return False

    mismatches = 0
    for image_id, parallel_item in parallel_items.items():
        sequential_item = sequential_items.get(image_id)
        if sequential_item is None:
            print(f"   ❌ FAILED: Image ID {image_id} missing in sequential build")
            mismatches += 1
            continue

        if parallel_item["hash"] != sequential_item["hash"]:
            print(f"   ❌ FAILED: Hash mismatch for {parallel_item['path']}")
            print(f"      Parallel:   {parallel_item['hash']}")
            print(f"      Sequential: {sequential_item['hash']}")
            mismatches += 1

    if mismatches == 0:
        print(f"   ✓ All {len(parallel_items)} hashes match!")

        if sequential_time > 0:
            speedup = sequential_time / parallel_time
            print("\n4. Performance:")
            print(f"   Parallel:   {parallel_time:.2f}s")
            print(f"   Sequential: {sequential_time:.2f}s")
            print(f"   Speedup:    {speedup:.2f}x")

        print("\n" + "=" * 60)
        print("✅ TEST PASSED: Parallel implementation is correct!")
        print("=" * 60)
        return True
    else:
        print(f"\n   ❌ FAILED: {mismatches} hash mismatches found")
        return False


if __name__ == "__main__":
    success = test_index_building()
    sys.exit(0 if success else 1)
