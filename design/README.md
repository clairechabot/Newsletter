# Design references — Botanical Editorial

Static source-of-truth mockups for the newsletter's "Botanical Editorial" look.
These files are **not** loaded at runtime — the live CSS/markup is generated inline
by `renderer.py` (email) and `webpage.py` (interactive web edition). Keep them here
as the canonical design reference when tweaking the look.

| File           | Mirrors                                              |
| -------------- | ---------------------------------------------------- |
| `email.html`   | The email cover that `renderer.py` builds            |
| `edition.html` | The full web edition that `webpage.py` builds        |
| `index.html`   | Landing/preview mockup                               |
| `tokens.css`   | Design tokens (palette, type) shared by the above    |
