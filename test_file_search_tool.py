"""
Direct test of find_document_by_context tool to verify ExecutionResult structure.
This tests the tool in isolation without going through the full pipeline.
"""

import sys
import os

# Add the project root to the path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

print("=" * 80)
print("DIRECT TOOL TEST - find_document_by_context")
print("=" * 80)

# Import the tool
from automation.file_context_search_tool import find_document_by_context

# Test 1: Search mode with a query
print("\n" + "=" * 80)
print("TEST 1: Search mode with query")
print("=" * 80)

test_query = "HealthSphere document"
print(f"Calling tool with query: '{test_query}'")

result = find_document_by_context({"query": test_query})

print("\n" + "=" * 80)
print("RESULT ANALYSIS")
print("=" * 80)
print(f"Success: {result.success}")
print(f"Tool: {result.tool}")
print(f"Message: {result.message}")
print(f"Requires Interaction: {getattr(result, 'requires_interaction', None)}")
print(f"Data: {getattr(result, 'data', None)}")
print(f"Output: {getattr(result, 'output', None)}")
print(f"Output type: {type(getattr(result, 'output', None))}")
print(f"Output length: {len(getattr(result, 'output', '')) if getattr(result, 'output', None) else 0}")

print("\n" + "=" * 80)
print("FULL RESULT DICT")
print("=" * 80)
print(result.to_dict())

print("\n" + "=" * 80)
print("DATA.RESULTS ANALYSIS")
print("=" * 80)
if hasattr(result, 'data') and result.data:
    results = result.data.get('results', [])
    print(f"Results count: {len(results)}")
    for i, r in enumerate(results):
        print(f"\nResult {i+1}:")
        print(f"  Keys: {list(r.keys())}")
        print(f"  Filename: {r.get('filename')}")
        print(f"  Path: {r.get('path')}")
        print(f"  Folder: {r.get('folder_path')}")
else:
    print("No data or no results in data")

# Test 2: Check if requires_interaction is True
print("\n" + "=" * 80)
print("CRITICAL CHECK: requires_interaction flag")
print("=" * 80)
if hasattr(result, 'requires_interaction'):
    if result.requires_interaction:
        print("✓ requires_interaction is TRUE - CORRECT")
    else:
        print("✗ requires_interaction is FALSE - INCORRECT - This is the bug!")
else:
    print("✗ requires_interaction attribute is MISSING - INCORRECT - This is the bug!")

print("\n" + "=" * 80)
print("TEST COMPLETE")
print("=" * 80)
