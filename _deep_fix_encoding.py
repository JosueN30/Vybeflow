"""Comprehensive mojibake scanner and fixer using cp1252 -> utf-8 reversal."""
import re
import os

def build_fix_map(content):
    """Find all cp1252-encoded sequences and build a replacement map."""
    fix_map = {}
    # Match sequences of non-ASCII chars (2 to 4 characters)
    for m in re.finditer(r'[^\x00-\x7f]{2,4}', content):
        mojibake = m.group()
        if mojibake in fix_map:
            continue
        try:
            raw = mojibake.encode('cp1252')
            decoded = raw.decode('utf-8')
            # Only fix if result has higher codepoints (likely emoji/symbol)
            if len(decoded) == 1 and ord(decoded) > 0x00B0:
                fix_map[mojibake] = decoded
            elif len(decoded) <= 2 and all(ord(c) > 0x2000 for c in decoded):
                fix_map[mojibake] = decoded
        except (UnicodeEncodeError, UnicodeDecodeError):
            pass
    return fix_map

def fix_file(path, preview=False):
    try:
        with open(path, 'r', encoding='utf-8') as f:
            content = f.read()
    except Exception as e:
        print(f'SKIP {path}: {e}')
        return 0

    fix_map = build_fix_map(content)
    if not fix_map:
        return 0

    if preview:
        print(f'\n{path}: {len(fix_map)} patterns to fix')
        for bad, good in sorted(fix_map.items()):
            count = content.count(bad)
            print(f'  {repr(bad)} x{count} -> {repr(good)} ({good})')

    fixed = content
    total = 0
    for bad, good in fix_map.items():
        n = fixed.count(bad)
        fixed = fixed.replace(bad, good)
        total += n

    if total:
        with open(path, 'w', encoding='utf-8') as f:
            f.write(fixed)
        print(f'Fixed {total} instances across {len(fix_map)} patterns in {path}')
    return total

grand_total = 0
for fname in os.listdir('templates'):
    if fname.endswith('.html'):
        grand_total += fix_file(os.path.join('templates', fname), preview=True)

print(f'\nGrand total fixed: {grand_total}')
