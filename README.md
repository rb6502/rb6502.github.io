# rb6502.github.io

Source for [Arbee's WIP Emporium](https://rb6502.github.io/). Posts are Markdown
files in `posts/`; `build.py` turns them into a static site in `docs/`, which
GitHub Pages serves as-is.

## Writing a post

```sh
make new TITLE="Pippin boots to Finder"   # creates posts/YYYY-MM-DD-pippin-boots-to-finder.md
$EDITOR posts/2026-...-pippin-boots-to-finder.md
make serve                                # preview at http://localhost:8000/
make                                      # build docs/ for publishing
git add -A && git commit -m "New post" && git push
```

The first `make` creates a local Python venv in `.venv/` and installs the
[Markdown](https://python-markdown.github.io/) package into it. Without make, the
same commands are `python3 build.py`, `python3 build.py serve`, and
`python3 build.py new "Title"` (run with a Python that has `Markdown` installed).

`make serve` doesn't watch for changes; stop it and run it again after editing.

### Post format

```markdown
---
title: I need your clothes, your boots, and your motorcycle
date: 2026-06-16 12:53
tags: General, PowerPC
---

Post text in Markdown...
```

| Field   | Required | Notes |
|---------|----------|-------|
| `title` | yes      | |
| `date`  | no       | `YYYY-MM-DD` or `YYYY-MM-DD HH:MM` in the timezone from `site.toml`. Defaults to the date in the file name. If a time is given it's shown as "@ 12:53 pm". |
| `tags`  | no       | Comma-separated. Each tag gets a page at `/tags/<tag>/`. |
| `slug`  | no       | Overrides the URL slug, which otherwise comes from the file name. |
| `draft` | no       | `draft: true` keeps the post out of `docs/`. `make preview` shows drafts (built into `.preview/`, which is never published). |

Post URLs look like `/2026/06/16/i-need-your-clothes-your-boots-and-your-motorcycle/`.

Markdown extras that are turned on: tables, fenced code blocks, footnotes,
`{: .class }` attribute lists, and "smart" punctuation (straight quotes become
curly, `--` becomes an en dash, `---` an em dash, `...` an ellipsis). Raw HTML
works too, e.g. for `<figure>` or `<video>`.

### Images and other files

Anything in `static/` is copied to the root of the site. Put screenshots in
`static/images/` and reference them with an absolute path:

```markdown
![Pippin startup screen](/images/pippin-startup.png)
```

## Layout

| Path                | What it is |
|---------------------|------------|
| `posts/`            | Your posts (Markdown). |
| `site.toml`         | Site title, tagline, URL, timezone, posts per page, sidebar links. |
| `templates/page.html` | HTML wrapper for every page. |
| `static/`           | Stylesheet, header image, and any other files to publish. |
| `build.py`          | The generator. |
| `docs/`             | Generated output. **Don't edit by hand**: it's deleted and rebuilt on every build. To publish an extra file (e.g. a `CNAME` for a custom domain), put it in `static/`. |

The build generates the front page (with older posts on `/page/2/` and so on),
one page per post, `/archive/`, a page per tag, an Atom feed at `/feed.xml`,
and `404.html`.

## GitHub Pages setup (one time)

In the repository on GitHub: **Settings → Pages → Build and deployment**, set
**Source** to *Deploy from a branch*, **Branch** to `master`, folder `/docs`, and save.
After that, every push that includes an updated `docs/` republishes the site within a minute or two.
