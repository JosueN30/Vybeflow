import os

# Build replacement list: bytes E2 9A 99 etc. decoded as cp1252 give the mojibake
# e.g.  0xE2=â  0x9A=š  0x99=™  -> âš™  but should be ⚙ (U+2699, UTF-8: E2 9A 99)
RAW = [
    (b'\xe2\x9a\x99', '\u2699'),   # ⚙ gear
    (b'\xe2\x9c\x95', '\u2715'),   # ✕ ballot X
    (b'\xe2\x9c\x93', '\u2713'),   # ✓ check
    (b'\xe2\x86\x91', '\u2191'),   # ↑
    (b'\xe2\x86\x93', '\u2193'),   # ↓
    (b'\xe2\x86\x90', '\u2190'),   # ←
    (b'\xe2\x86\x92', '\u2192'),   # →
    (b'\xe2\x96\xb6', '\u25b6'),   # ▶
    (b'\xe2\x96\xb8', '\u25b8'),   # ▸
    (b'\xe2\x96\xbd', '\u25bd'),   # ▽
    (b'\xe2\x96\xbe', '\u25be'),   # ▾
    (b'\xe2\x94\x80', '\u2500'),   # ─
    (b'\xe2\x94\x82', '\u2502'),   # │
    (b'\xe2\x95\x90', '\u2550'),   # ═
    (b'\xe2\x95\x91', '\u2551'),   # ║
    (b'\xe2\x95\x94', '\u2554'),   # ╔
    (b'\xe2\x95\x97', '\u2557'),   # ╗
    (b'\xe2\x95\x9a', '\u255a'),   # ╚
    (b'\xe2\x95\x9d', '\u255d'),   # ╝
    (b'\xe2\x80\x94', '\u2014'),   # — em dash
    (b'\xe2\x80\x93', '\u2013'),   # – en dash
    (b'\xe2\x80\x99', '\u2019'),   # ' right single quote
    (b'\xe2\x80\x98', '\u2018'),   # ' left single quote
    (b'\xe2\x80\x9c', '\u201c'),   # " left double quote
    (b'\xe2\x80\x9d', '\u201d'),   # " right double quote
    (b'\xe2\x80\xa6', '\u2026'),   # … ellipsis
    (b'\xe2\x84\xa2', '\u2122'),   # ™ trademark
    (b'\xc2\xae', '\u00ae'),       # ® registered
    (b'\xc2\xa9', '\u00a9'),       # © copyright
    (b'\xc2\xb7', '\u00b7'),       # · middle dot
    (b'\xc3\x97', '\u00d7'),       # × multiplication
    (b'\xc3\xb7', '\u00f7'),       # ÷ division
]

REPLACEMENTS = []
for raw_bytes, correct in RAW:
    try:
        mojibake = raw_bytes.decode('cp1252')
        REPLACEMENTS.append((mojibake, correct))
    except Exception:
        pass

def fix_file(path):
    try:
        with open(path, 'r', encoding='utf-8') as f:
            content = f.read()
    except Exception as e:
        print(f'SKIP {path}: {e}')
        return 0
    fixed = content
    count = 0
    for bad, good in REPLACEMENTS:
        n = fixed.count(bad)
        if n:
            fixed = fixed.replace(bad, good)
            count += n
    if count:
        with open(path, 'w', encoding='utf-8') as f:
            f.write(fixed)
        print(f'Fixed {count} patterns in {path}')
    return count

total = 0
for fname in os.listdir('templates'):
    if fname.endswith('.html'):
        total += fix_file(os.path.join('templates', fname))
for fname in os.listdir('.'):
    if fname.endswith('.py') and not fname.startswith('_'):
        total += fix_file(fname)
if os.path.isdir('routes'):
    for fname in os.listdir('routes'):
        if fname.endswith('.py'):
            total += fix_file(os.path.join('routes', fname))
print(f'Total: {total} replacements')
