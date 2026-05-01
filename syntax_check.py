"""Quick syntax and import check for app.py"""
import sys
sys.path.insert(0, 'd:\\Vybeflow-main')

# First check Python syntax
import ast
try:
    with open('app.py', 'r', encoding='utf-8') as f:
        source = f.read()
    tree = ast.parse(source)
    print("OK: app.py syntax is valid")
except SyntaxError as e:
    print(f"SYNTAX ERROR in app.py: {e}")
    sys.exit(1)

# Check for remaining duplicate endpoints
import re
from collections import Counter

routes = re.findall(r'@app\.(?:route|get|post|put|delete|patch)\(["\']([^"\']*)', source)
counts = Counter(routes)
dupes = {k: v for k, v in counts.items() if v > 1}
if dupes:
    print("WARNING: Duplicate route paths:")
    for k, v in sorted(dupes.items()):
        print(f"  {v}x {k}")
else:
    print("OK: No duplicate route paths")

print("Check complete.")
