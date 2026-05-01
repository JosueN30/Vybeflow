"""Fix mojibake in ALL template files and static JS/CSS files using ftfy."""
import ftfy
import os
import shutil

EXTS = ('.html', '.js', '.css', '.py')

def fix_file(path):
    try:
        with open(path, 'r', encoding='utf-8', errors='replace') as f:
            original = f.read()
    except Exception as e:
        print(f'  SKIP (read error): {path}: {e}')
        return 0

    fixed = ftfy.fix_text(original)
    if fixed == original:
        return 0  # nothing to fix

    # Backup
    bak = path + '.bak_enc'
    if not os.path.exists(bak):
        shutil.copy2(path, bak)

    with open(path, 'w', encoding='utf-8') as f:
        f.write(fixed)

    before_len = len(original)
    after_len = len(fixed)
    print(f'  FIXED: {path} ({before_len - after_len:+d} chars)')
    return 1

total = 0

# Fix all templates
for fname in os.listdir('templates'):
    if fname.endswith('.html'):
        total += fix_file(os.path.join('templates', fname))

# Fix static JS files
for root, dirs, files in os.walk('static'):
    for fname in files:
        if fname.endswith('.js') and not fname.endswith('.min.js'):
            total += fix_file(os.path.join(root, fname))

# Fix Python route files (they have user-facing strings too)
for fname in os.listdir('.'):
    if fname.endswith('.py') and fname not in ('_fix_all_encoding.py', '_fix_encoding.py'):
        total += fix_file(fname)
for fname in os.listdir('routes') if os.path.isdir('routes') else []:
    if fname.endswith('.py'):
        total += fix_file(os.path.join('routes', fname))

print(f'\nTotal files fixed: {total}')
print('Done! Run smoke_test.py to verify.')
