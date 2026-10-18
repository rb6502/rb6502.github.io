#!/usr/bin/env python3
"""Static blog generator for rb6502.github.io.

    python3 build.py                  build the site into docs/
    python3 build.py serve [PORT]     build, then preview at http://localhost:8000/
    python3 build.py serve --drafts   same, but include drafts (built into .preview/, never docs/)
    python3 build.py new "Title"      start a new post in posts/

See README.md for the post format.
"""

import datetime as dt
import html
import re
import shutil
import string
import sys
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from zoneinfo import ZoneInfo

try:
    import markdown
except ImportError:
    sys.exit(
        "The Python 'Markdown' package isn't installed.\n"
        "Run 'make' (which sets up .venv for you), or:\n"
        "    python3 -m venv .venv && .venv/bin/pip install -r requirements.txt\n"
        "    .venv/bin/python build.py"
    )

ROOT = Path(__file__).resolve().parent
POSTS_DIR = ROOT / "posts"
STATIC_DIR = ROOT / "static"
TEMPLATE_FILE = ROOT / "templates" / "page.html"
OUT_DIR = ROOT / "docs"
PREVIEW_DIR = ROOT / ".preview"

FILENAME_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})-(.+)$")
MARKDOWN_EXTENSIONS = ["extra", "smarty", "sane_lists"]


class BuildError(Exception):
    pass


@dataclass
class Post:
    source: Path
    title: str
    date: dt.datetime
    has_time: bool
    slug: str
    tags: list[str]
    body_html: str
    draft: bool = False
    summary: str = field(default="")

    @property
    def url(self) -> str:
        return f"/{self.date:%Y/%m/%d}/{self.slug}/"


# ---------------------------------------------------------------------------
# Helpers

def esc(text: str) -> str:
    return html.escape(text, quote=True)


def esc_text(text: str) -> str:
    """Escape plain config text (titles, link names) with typographic apostrophes."""
    return esc(re.sub(r"(?<=\S)'", "\u2019", text))


def slugify(text: str) -> str:
    text = re.sub(r"[^a-z0-9]+", "-", text.lower())
    return text.strip("-") or "post"


def display_date(d: dt.datetime) -> str:
    return f"{d:%B} {d.day}, {d.year}"


def display_time(d: dt.datetime) -> str:
    hour = d.hour % 12 or 12
    return f"{hour}:{d:%M} {'am' if d.hour < 12 else 'pm'}"


def strip_tags(fragment: str) -> str:
    return html.unescape(re.sub(r"<[^>]+>", "", fragment))


def make_summary(body_html: str, limit: int = 200) -> str:
    match = re.search(r"<p>(.*?)</p>", body_html, re.S)
    text = " ".join(strip_tags(match.group(1) if match else body_html).split())
    if len(text) > limit:
        text = text[:limit].rsplit(" ", 1)[0] + "…"
    return text


# ---------------------------------------------------------------------------
# Reading posts

def parse_front_matter(text: str, path: Path) -> tuple[dict, str]:
    """Split simple 'key: value' front matter (between --- lines) from the body."""
    lines = text.splitlines(keepends=True)
    if not lines or lines[0].strip() != "---":
        return {}, text
    meta = {}
    for i, line in enumerate(lines[1:], start=1):
        stripped = line.strip()
        if stripped == "---":
            return meta, "".join(lines[i + 1:])
        if not stripped or stripped.startswith("#"):
            continue
        key, sep, value = line.partition(":")
        if not sep:
            raise BuildError(f"{path.name}: can't read front matter line {i + 1}: {stripped!r}")
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        meta[key.strip().lower()] = value
    raise BuildError(f"{path.name}: front matter has no closing '---' line")


def parse_date(value: str, path: Path, tz: ZoneInfo) -> tuple[dt.datetime, bool]:
    for fmt, has_time in (("%Y-%m-%d %H:%M:%S", True), ("%Y-%m-%d %H:%M", True), ("%Y-%m-%d", False)):
        try:
            return dt.datetime.strptime(value.strip(), fmt).replace(tzinfo=tz), has_time
        except ValueError:
            pass
    raise BuildError(f"{path.name}: date {value!r} should look like 2026-06-16 or 2026-06-16 12:53")


def read_post(path: Path, md: markdown.Markdown, tz: ZoneInfo) -> Post:
    meta, body = parse_front_matter(path.read_text(encoding="utf-8"), path)

    title = meta.get("title", "").strip()
    if not title:
        raise BuildError(f"{path.name}: missing 'title:' in front matter")

    name_match = FILENAME_RE.match(path.stem)
    if "date" in meta:
        date, has_time = parse_date(meta["date"], path, tz)
    elif name_match:
        date, has_time = parse_date(name_match.group(1), path, tz)
    else:
        raise BuildError(f"{path.name}: no 'date:' in front matter and no date at the start of the file name")

    slug = slugify(meta.get("slug") or (name_match.group(2) if name_match else path.stem))
    tags = [t.strip() for t in meta.get("tags", "").split(",") if t.strip()]
    draft = meta.get("draft", "").lower() in ("true", "yes", "1")

    md.reset()
    body_html = md.convert(body)
    return Post(path, title, date, has_time, slug, tags, body_html, draft, make_summary(body_html))


def load_posts(md: markdown.Markdown, tz: ZoneInfo, include_drafts: bool) -> list[Post]:
    posts = []
    for path in sorted(POSTS_DIR.glob("*.md")):
        post = read_post(path, md, tz)
        if post.draft and not include_drafts:
            print(f"  skipping draft: {path.name}")
            continue
        posts.append(post)

    seen = {}
    for post in posts:
        if post.url in seen:
            raise BuildError(f"{post.source.name} and {seen[post.url].name} both map to {post.url}")
        seen[post.url] = post.source

    posts.sort(key=lambda p: (p.date, p.source.name), reverse=True)
    return posts


# ---------------------------------------------------------------------------
# Rendering

class Site:
    def __init__(self, config: dict, posts: list[Post], out_dir: Path):
        self.config = config
        self.posts = posts
        self.out_dir = out_dir
        self.base_url = config["url"].rstrip("/")
        self.template = string.Template(TEMPLATE_FILE.read_text(encoding="utf-8"))
        self.tags: dict[str, list[Post]] = {}
        for post in posts:
            for tag in post.tags:
                self.tags.setdefault(tag, []).append(post)
        self.sidebar = self.render_sidebar()
        self.pages_written = 0

    # -- output --

    def write(self, url_path: str, text: str) -> None:
        """Write a page. url_path ending in '/' becomes .../index.html."""
        rel = url_path.lstrip("/")
        if rel == "" or rel.endswith("/"):
            rel += "index.html"
        target = self.out_dir / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
        self.pages_written += 1

    def page(self, url_path: str, content: str, title: str | None = None,
             description: str | None = None, og_type: str = "website") -> None:
        cfg = self.config
        page_title = f"{title} | {cfg['title']}" if title else cfg["title"]
        self.write(url_path, self.template.substitute(
            page_title=esc(page_title),
            og_title=esc(title or cfg["title"]),
            og_type=og_type,
            site_title=esc_text(cfg["title"]),
            tagline=esc_text(cfg.get("tagline", "")),
            description=esc(description or cfg.get("tagline", "")),
            canonical=esc(self.base_url + url_path),
            header_image=esc(cfg["header_image"]),
            author=esc(cfg.get("author", "")),
            year=dt.date.today().year,
            content=content,
            sidebar=self.sidebar,
        ))

    # -- fragments --

    def tag_url(self, tag: str) -> str:
        return f"/tags/{slugify(tag)}/"

    def render_post(self, post: Post, permalink_page: bool = False) -> str:
        heading = "h1" if permalink_page else "h2"
        title = esc(post.title) if permalink_page else f'<a href="{post.url}">{esc(post.title)}</a>'
        meta = f"Posted by {esc(self.config.get('author', ''))}"
        if post.tags:
            meta += " in " + ", ".join(
                f'<a href="{self.tag_url(t)}">{esc(t)}</a>' for t in post.tags)
        if post.has_time:
            meta += f" @ {display_time(post.date)}"
        if not permalink_page:
            meta += f' &middot; <a href="{post.url}">Permalink</a>'
        draft = ' <span class="draft-badge">Draft</span>' if post.draft else ""
        return f"""<article class="post">
  <header class="post-header">
    <p class="post-date"><time datetime="{post.date.isoformat()}">{display_date(post.date)}</time>{draft}</p>
    <{heading} class="post-title">{title}</{heading}>
  </header>
  <div class="post-body">
{post.body_html}
  </div>
  <footer class="post-meta">{meta}</footer>
</article>"""

    def render_post_list(self, posts: list[Post]) -> str:
        items = "\n".join(
            f'  <li><time datetime="{p.date:%Y-%m-%d}">{display_date(p.date)}</time> '
            f'<a href="{p.url}">{esc(p.title)}</a></li>'
            for p in posts)
        return f'<ul class="post-list">\n{items}\n</ul>'

    def render_sidebar(self) -> str:
        parts = []

        recent = "\n".join(f'    <li><a href="{p.url}">{esc(p.title)}</a></li>' for p in self.posts[:5])
        if recent:
            parts.append(f'  <section>\n    <h2>Recent posts</h2>\n    <ul>\n{recent}\n    </ul>\n  </section>')

        months: dict[tuple[int, int], int] = {}
        for p in self.posts:
            months[(p.date.year, p.date.month)] = months.get((p.date.year, p.date.month), 0) + 1
        if months:
            items = "\n".join(
                f'    <li><a href="/archive/#{y}-{m:02d}">{dt.date(y, m, 1):%B} {y}</a> <span class="count">({n})</span></li>'
                for (y, m), n in months.items())
            parts.append(f'  <section>\n    <h2>Archives</h2>\n    <ul>\n{items}\n    </ul>\n  </section>')

        if self.tags:
            items = "\n".join(
                f'    <li><a href="{self.tag_url(t)}">{esc(t)}</a> <span class="count">({len(ps)})</span></li>'
                for t, ps in sorted(self.tags.items(), key=lambda kv: kv[0].lower()))
            parts.append(f'  <section>\n    <h2>Tags</h2>\n    <ul>\n{items}\n    </ul>\n  </section>')

        links = self.config.get("links", [])
        if links:
            items = "\n".join(f'    <li><a href="{esc(l["url"])}">{esc_text(l["name"])}</a></li>' for l in links)
            parts.append(f'  <section>\n    <h2>Links</h2>\n    <ul>\n{items}\n    </ul>\n  </section>')

        parts.append('  <section>\n    <h2>Subscribe</h2>\n    <ul>\n'
                     '    <li><a href="/feed.xml">Atom feed</a></li>\n    </ul>\n  </section>')
        return "\n".join(parts)

    # -- pages --

    def build_index_pages(self) -> None:
        per_page = max(1, int(self.config.get("posts_on_front_page", 10)))
        chunks = [self.posts[i:i + per_page] for i in range(0, len(self.posts), per_page)] or [[]]

        def page_url(n: int) -> str:
            return "/" if n == 1 else f"/page/{n}/"

        for n, chunk in enumerate(chunks, start=1):
            body = "\n\n".join(self.render_post(p) for p in chunk) or '<p class="empty">No posts yet.</p>'
            nav = []
            if n > 1:
                nav.append(f'<a class="newer" href="{page_url(n - 1)}">&larr; Newer posts</a>')
            if n < len(chunks):
                nav.append(f'<a class="older" href="{page_url(n + 1)}">Older posts &rarr;</a>')
            if nav:
                body += f'\n<nav class="pager">{" ".join(nav)}</nav>'
            self.page(page_url(n), body, title=None if n == 1 else f"Page {n}")

    def build_post_pages(self) -> None:
        for i, post in enumerate(self.posts):
            newer = self.posts[i - 1] if i > 0 else None
            older = self.posts[i + 1] if i + 1 < len(self.posts) else None
            nav = []
            if older:
                nav.append(f'<a class="older-post" href="{older.url}">&larr; {esc(older.title)}</a>')
            if newer:
                nav.append(f'<a class="newer-post" href="{newer.url}">{esc(newer.title)} &rarr;</a>')
            body = self.render_post(post, permalink_page=True)
            if nav:
                body += f'\n<nav class="pager post-pager">{" ".join(nav)}</nav>'
            self.page(post.url, body, title=post.title, description=post.summary, og_type="article")

    def build_archive(self) -> None:
        sections = []
        current = None
        group: list[Post] = []

        def flush():
            if current:
                y, m = current
                sections.append(f'<h2 id="{y}-{m:02d}">{dt.date(y, m, 1):%B} {y}</h2>\n'
                                + self.render_post_list(group))

        for post in self.posts:
            key = (post.date.year, post.date.month)
            if key != current:
                flush()
                current, group = key, []
            group.append(post)
        flush()

        body = '<h1 class="page-title">Archive</h1>\n' + ("\n".join(sections) or '<p class="empty">No posts yet.</p>')
        self.page("/archive/", body, title="Archive")

    def build_tag_pages(self) -> None:
        for tag, posts in self.tags.items():
            body = f'<h1 class="page-title">Posts tagged &ldquo;{esc(tag)}&rdquo;</h1>\n' + self.render_post_list(posts)
            self.page(self.tag_url(tag), body, title=f"Tagged {tag}")

    def build_404(self) -> None:
        body = ('<h1 class="page-title">Page not found</h1>\n'
                '<p>That page doesn\'t exist. Try the <a href="/">front page</a> '
                'or the <a href="/archive/">archive</a>.</p>')
        self.page("/404.html", body, title="Page not found")  # GitHub Pages serves this for missing URLs

    def build_feed(self) -> None:
        cfg = self.config
        base = self.base_url

        def absolutize(fragment: str) -> str:
            return re.sub(r'(\s(?:href|src))="/(?!/)', rf'\1="{base}/', fragment)

        entries = []
        for post in self.posts[: int(cfg.get("feed_entries", 20))]:
            categories = "".join(f'\n    <category term="{esc(t)}"/>' for t in post.tags)
            entries.append(f"""  <entry>
    <title>{esc(post.title)}</title>
    <link href="{base}{post.url}"/>
    <id>{base}{post.url}</id>
    <published>{post.date.isoformat()}</published>
    <updated>{post.date.isoformat()}</updated>{categories}
    <content type="html">{esc(absolutize(post.body_html))}</content>
  </entry>""")

        updated = (self.posts[0].date if self.posts else dt.datetime.now(dt.timezone.utc)).isoformat()
        feed = f"""<?xml version="1.0" encoding="utf-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <title>{esc(cfg['title'])}</title>
  <subtitle>{esc(cfg.get('tagline', ''))}</subtitle>
  <link href="{base}/feed.xml" rel="self"/>
  <link href="{base}/"/>
  <id>{base}/</id>
  <updated>{updated}</updated>
  <author><name>{esc(cfg.get('author', ''))}</name></author>
{chr(10).join(entries)}
</feed>
"""
        (self.out_dir / "feed.xml").write_text(feed, encoding="utf-8")
        self.pages_written += 1

    def build(self) -> None:
        self.build_index_pages()
        self.build_post_pages()
        self.build_archive()
        self.build_tag_pages()
        self.build_404()
        self.build_feed()


# ---------------------------------------------------------------------------
# Commands

def load_config() -> dict:
    with open(ROOT / "site.toml", "rb") as f:
        config = tomllib.load(f)
    for key in ("title", "url", "header_image"):
        if key not in config:
            raise BuildError(f"site.toml is missing '{key}'")
    return config


def build(include_drafts: bool = False) -> Path:
    config = load_config()
    tz = ZoneInfo(config.get("timezone", "UTC"))
    out_dir = PREVIEW_DIR if include_drafts else OUT_DIR

    md = markdown.Markdown(extensions=MARKDOWN_EXTENSIONS, output_format="html")
    posts = load_posts(md, tz, include_drafts)

    # The output folder is fully generated, so start clean to drop deleted posts.
    if out_dir.exists():
        shutil.rmtree(out_dir)
    out_dir.mkdir()
    shutil.copytree(STATIC_DIR, out_dir, dirs_exist_ok=True)
    (out_dir / ".nojekyll").touch()  # serve files as-is; don't run GitHub's Jekyll

    site = Site(config, posts, out_dir)
    site.build()
    print(f"Built {len(posts)} post(s), {site.pages_written} file(s) into {out_dir.relative_to(ROOT)}/")
    return out_dir


def serve(args: list[str]) -> None:
    import functools
    import http.server

    include_drafts = "--drafts" in args
    ports = [a for a in args if a.isdigit()]
    port = int(ports[0]) if ports else 8000

    out_dir = build(include_drafts)
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(out_dir))
    with http.server.ThreadingHTTPServer(("127.0.0.1", port), handler) as httpd:
        print(f"Previewing at http://localhost:{port}/  (Ctrl+C to stop; re-run to pick up edits)")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print()


def new_post(args: list[str]) -> None:
    title = " ".join(args).strip()
    if not title:
        raise BuildError('usage: build.py new "Post title"')
    config = load_config()
    now = dt.datetime.now(ZoneInfo(config.get("timezone", "UTC")))
    path = POSTS_DIR / f"{now:%Y-%m-%d}-{slugify(title)}.md"
    if path.exists():
        raise BuildError(f"{path.relative_to(ROOT)} already exists")
    POSTS_DIR.mkdir(exist_ok=True)
    safe_title = f'"{title}"' if title[0] in "\"'" else title
    path.write_text(f"---\ntitle: {safe_title}\ndate: {now:%Y-%m-%d %H:%M}\ntags: General\n---\n\n", encoding="utf-8")
    print(f"Created {path.relative_to(ROOT)}")


def main(argv: list[str]) -> int:
    try:
        if not argv or argv[0] == "build":
            build()
        elif argv[0] == "serve":
            serve(argv[1:])
        elif argv[0] == "new":
            new_post(argv[1:])
        else:
            print(__doc__)
            return 1
    except BuildError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
