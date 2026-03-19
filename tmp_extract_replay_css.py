from pathlib import Path
import re

html_path = Path(r"d:/docker/atas-market-structure/src/atas_market_structure/static/replay_workbench.html")
css_path = Path(r"d:/docker/atas-market-structure/src/atas_market_structure/static/replay_workbench.css")

text = html_path.read_text(encoding="utf-8")
match = re.search(r"<style>\s*(.*?)\s*</style>", text, re.S)
if not match:
    raise SystemExit("style block not found")

css = match.group(1).rstrip() + "\n"
css_path.write_text(css, encoding="utf-8")
link = '  <link rel="stylesheet" href="./replay_workbench.css">\n'
text = text[:match.start()] + link + text[match.end():]
html_path.write_text(text, encoding="utf-8")
print("ok")
