import os
import sys

# Loyiha ildizi sys.path ga (skript scripts/ ichidan ishga tushirilganda)
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'bek_burger.settings')
"""
Shablonlardagi <script> bloklarini sintaktik tekshiradi (node --check).

Ishga tushirish:  python _js_check.py
"""
import os
import re
import subprocess
import sys
import tempfile


import django

django.setup()

from django.template.loader import get_template

TEMPLATES = [
    'miniapp/customer/index.html',
    'miniapp/director/dashboard.html',
    'miniapp/chef/index.html',
    'miniapp/courier/index.html',
]

SCRIPT_RE = re.compile(r'<script(?![^>]*\bsrc=)[^>]*>(.*?)</script>', re.S | re.I)

# Django templating taglari JS da ishlatilmaydi — ularni placeholder ga almashtiramiz
TAGS = [
    (r'{%\s*csrf_token[^%]*%}', "''"),
    (r'{%\s*static\s+[\'"][^\'"]+[\'"]\s*%}', "''"),
    (r'{%\s*url\s+[\'"][^\'"]+[\'"]\s*%}', "'/'"),
    (r'{%\s*if[^%]*%}|{%\s*endif\s*%}|{%\s*else\s*%}|{%\s*for[^%]*%}|{%\s*empty\s*%}', ''),
    (r'{%\s*blocktrans[^%]*%}|{%\s*endblocktrans\s*%}', ''),
    (r'{%\s*comment\s*%}|{%\s*endcomment\s*%}', ''),
    (r'{{[^}]*}}', 'null'),
    (r'{%\s*\w+[^%]*%}', ''),
]

failures = 0
total = 0

for tpl in TEMPLATES:
    src = get_template(tpl).template.source
    blocks = SCRIPT_RE.findall(src)
    if not blocks:
        print('  SKIP  {} (inline script yo\'q)'.format(tpl))
        continue
    for i, code in enumerate(blocks, 1):
        for pattern, repl in TAGS:
            code = re.sub(pattern, repl, code)
        total += 1
        with tempfile.NamedTemporaryFile('w', suffix='.js', delete=False, encoding='utf-8') as f:
            f.write(code)
            path = f.name
        proc = subprocess.run(['node', '--check', path], capture_output=True, text=True)
        os.unlink(path)
        if proc.returncode == 0:
            print('  OK    {} [script #{}]'.format(tpl, i))
        else:
            failures += 1
            print('  FAIL  {} [script #{}]'.format(tpl, i))
            for line in proc.stderr.strip().splitlines()[:6]:
                print('          ' + line)

print()
print('JS sintaksisi: {} / {} blok to\'g\'ri'.format(total - failures, total))
sys.exit(1 if failures else 0)
