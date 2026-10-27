import pathlib

root = pathlib.Path(__file__).resolve().parents[1] / "components"
replacements = [
    ('fill="#94a3b8"', 'fill="hsl(var(--chart-axis))"'),
    ('fill="#64748b"', 'fill="hsl(var(--chart-axis))"'),
    ('stroke="#e2e8f0"', 'stroke="hsl(var(--chart-grid))"'),
    ('stroke="#eef2f7"', 'stroke="hsl(var(--chart-grid))"'),
    ('stroke="#cbd5e1"', 'stroke="hsl(var(--chart-grid))"'),
    ('stroke="#94a3b8"', 'stroke="hsl(var(--chart-axis))"'),
]
changed = 0
for p in root.rglob("*.tsx"):
    text = p.read_text(encoding="utf-8")
    orig = text
    for a, b in replacements:
        text = text.replace(a, b)
    if text != orig:
        p.write_text(text, encoding="utf-8")
        changed += 1
print("svg token files", changed)
