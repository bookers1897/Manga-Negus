#!/usr/bin/env python3
"""
Systematic Health Check for All MangaNegus Sources
Tests: availability, search, chapters, pages
"""
import sys
import json
from sources import get_source_manager

def test_source_health(source_id, source):
    """Test a single source's health"""
    result = {
        'id': source_id,
        'name': source.name,
        'base_url': source.base_url,
        'tests': {}
    }

    # Test 1: Basic search
    try:
        search_results = source.search("naruto", page=1)
        if search_results is None:
            result['tests']['search'] = 'FAIL - returned None'
        elif len(search_results) == 0:
            result['tests']['search'] = 'WARN - no results'
        else:
            result['tests']['search'] = f'PASS - {len(search_results)} results'
            result['first_manga'] = {
                'id': search_results[0].id,
                'title': search_results[0].title
            }
    except Exception as e:
        result['tests']['search'] = f'ERROR - {type(e).__name__}: {str(e)[:100]}'

    # Test 2: Get chapters (if search succeeded)
    if 'first_manga' in result:
        try:
            chapters = source.get_chapters(result['first_manga']['id'])
            if chapters is None:
                result['tests']['chapters'] = 'FAIL - returned None'
            elif len(chapters) == 0:
                result['tests']['chapters'] = 'WARN - no chapters'
            else:
                result['tests']['chapters'] = f'PASS - {len(chapters)} chapters'
                result['first_chapter'] = {
                    'id': chapters[0].id,
                    'chapter': chapters[0].chapter
                }
        except Exception as e:
            result['tests']['chapters'] = f'ERROR - {type(e).__name__}: {str(e)[:100]}'

    # Test 3: Get pages (if chapters succeeded)
    if 'first_chapter' in result:
        try:
            pages = source.get_pages(result['first_chapter']['id'])
            if pages is None:
                result['tests']['pages'] = 'FAIL - returned None'
            elif len(pages) == 0:
                result['tests']['pages'] = 'WARN - no pages'
            else:
                result['tests']['pages'] = f'PASS - {len(pages)} pages'
        except Exception as e:
            result['tests']['pages'] = f'ERROR - {type(e).__name__}: {str(e)[:100]}'

    return result

def main():
    print("=" * 80)
    print("MangaNegus Source Health Check")
    print("=" * 80)

    manager = get_source_manager()
    sources = manager.sources  # Dict[str, BaseConnector]

    print(f"\n📊 Testing {len(sources)} sources...\n")

    results = []
    for source_id, source in sources.items():

        print(f"Testing: {source.name} ({source_id})...")
        result = test_source_health(source_id, source)
        results.append(result)

        # Print summary
        status_symbols = {
            'PASS': '✅',
            'WARN': '⚠️',
            'FAIL': '❌',
            'ERROR': '💥'
        }
        for test_name, test_result in result['tests'].items():
            status = test_result.split(' - ')[0]
            symbol = status_symbols.get(status, '❓')
            print(f"  {symbol} {test_name}: {test_result}")
        print()

    # Summary statistics
    print("=" * 80)
    print("SUMMARY")
    print("=" * 80)

    total = len(results)
    working = sum(1 for r in results if any('PASS' in t for t in r['tests'].values()))
    broken = sum(1 for r in results if any('FAIL' in t or 'ERROR' in t for t in r['tests'].values()))

    print(f"\n📈 Overall: {working}/{total} sources partially working")
    print(f"❌ Broken: {broken}/{total} sources have failures\n")

    # Categorize issues
    print("BROKEN SOURCES:")
    for r in results:
        if any('FAIL' in t or 'ERROR' in t for t in r['tests'].values()):
            print(f"\n  ❌ {r['name']} ({r['id']})")
            for test_name, test_result in r['tests'].items():
                if 'FAIL' in test_result or 'ERROR' in test_result:
                    print(f"     - {test_name}: {test_result}")

    # Save detailed results
    with open('/home/kingwavy/projects/Manga-Negus/source_health_report.json', 'w') as f:
        json.dump(results, f, indent=2)

    print("\n💾 Detailed report saved to: source_health_report.json")
    print("=" * 80)

if __name__ == '__main__':
    main()
