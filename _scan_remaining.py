"""
Scan all template and JS files for remaining mojibake patterns that ftfy missed.
These are Windows-1252 sequences (â™ etc.) where the chars are valid Unicode
so ftfy's heuristic doesn't flag them, but they're clearly wrong in context.
"""
import os
import ftfy

def scan_file(path):
    try:
        with open(path, 'r', encoding='utf-8') as f:
            content = f.read()
    except Exception as e:
        return

    # Try ftfy with more aggressive settings
    fixed = ftfy.fix_text(content, fix_encoding=True, restore_byte_a0=True,
                          fix_latin_ligatures=True, fix_character_width=False,
                          uncurl_quotes=False, fix_line_breaks=False)
    
    remaining = []
    # Known Windows-1252 mojibake that look like valid text
    patterns = {
        'âš™': '⚙',   # gear
        'âœ•': '✕',   # ballot x
        'âœ"': '✓',   # check mark  
        '\u00e2\u2020\u2018': '\u2191',   # up arrow
        '\u00e2\u2020\u201d': '\u2193',   # down arrow
        '\u00e2\u2020\u2014': '\u2190',   # left arrow
        '\u00e2\u2020\u2019': '\u2192',   # right arrow
        'â–¶': '▶',   # right triangle
        'â–¸': '▸',   # right-pointing small triangle
        'â–½': '▽',   # white down-pointing triangle
        'â–¾': '▾',   # black down-pointing small triangle
        'âœ‹': '✋',   # raised hand
        'âŽ¤': '⏤',   # horizontal line
        'â²': '⊲',   # not sure, test
        'â•': '═',   # various box chars
        'â"€': '─',   # box drawing light horizontal
        'â"‚': '│',   # box drawing light vertical
    }
    
    for bad, good in patterns.items():
        if bad in fixed:
            print(f'  {path}: found {repr(bad)} (should be {repr(good)})')
            remaining.append((bad, good))

    if remaining:
        for bad, good in remaining:
            fixed = fixed.replace(bad, good)
        with open(path, 'w', encoding='utf-8') as f:
            f.write(fixed)
        print(f'  -> Fixed {len(remaining)} remaining patterns in {path}')

for fname in os.listdir('templates'):
    if fname.endswith('.html'):
        scan_file(os.path.join('templates', fname))
