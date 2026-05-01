"""Fix mojibake (garbled UTF-8 text) in feed.html using ftfy."""
import ftfy
import re
import shutil
import os

src = 'templates/feed.html'
bak = 'templates/feed.html.bak_encoding'

# Backup first
shutil.copy2(src, bak)
print(f'Backup created: {bak}')

with open(src, 'r', encoding='utf-8', errors='replace') as f:
    content = f.read()

print(f'Original length: {len(content)} chars')

# Count approximate mojibake: the 4-byte emoji encoded as latin-1 then re-encoded as utf-8
# shows up as sequences starting with \xc3\xb0 (Ã°) or \xc3\xb1 (Ã±) etc.
# In Python str after reading as UTF-8, these appear as characters like ð, Å, â, etc.
mojibake_before = len(re.findall(r'[\xc3-\xff][\x80-\xbf]', content.encode('latin-1', errors='replace').decode('latin-1')))
print(f'Mojibake sequences before: {mojibake_before}')

# Apply ftfy fix
fixed = ftfy.fix_text(content)

print(f'Fixed length: {len(fixed)} chars')

# Verify fixes
mojibake_after = len(re.findall(r'[\xc3-\xff][\x80-\xbf]', fixed.encode('latin-1', errors='replace').decode('latin-1')))
print(f'Mojibake sequences after: {mojibake_after}')

# Check that critical JS structure is preserved
checks = ['function renderPosts', 'createBtn.addEventListener', 'postsCache', 'vfUploadWithProgress']
for check in checks:
    if check not in fixed:
        print(f'WARNING: {check!r} not found in fixed content!')
    else:
        print(f'OK: {check!r} preserved')

# Check no new syntax errors (basic apostrophe check)
if "it's BLOWING UP" in fixed:
    print('ERROR: unescaped apostrophe found in fixed content!')
elif "it\\'s BLOWING UP" in fixed or 'it\\u2019s BLOWING UP' in fixed or "it\u2019s BLOWING UP" in fixed:
    print('OK: apostrophe safely escaped/encoded in fixed content')
else:
    print('INFO: apostrophe check skipped (string may have changed)')

with open(src, 'w', encoding='utf-8') as f:
    f.write(fixed)

print(f'Done! Fixed file written to {src}')
print(f'Backup is at {bak} if you need to revert')
