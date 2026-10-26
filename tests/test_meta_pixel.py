from pathlib import Path
import sys
root = Path(__file__).resolve().parents[1]
script = root / 'assets' / 'testes-meta-pixel.js'
if not script.exists():
    raise SystemExit('script do Meta Pixel ainda não existe')
text = script.read_text()
for token in ['1821967018037838', 'connect.facebook.net/en_US/fbevents.js', "fbq('track', 'PageView')", 'localStorage', 'Permitir medição', 'Agora não']:
    assert token in text, token
pages = [p for p in root.rglob('*.html') if '.git' not in p.parts]
missing = [str(p.relative_to(root)) for p in pages if '/assets/testes-meta-pixel.js' not in p.read_text()]
assert not missing, 'páginas sem carregador: ' + ', '.join(missing)
print(f'OK: {len(pages)} páginas usam Pixel somente após consentimento.')
