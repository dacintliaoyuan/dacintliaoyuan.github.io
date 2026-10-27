"""Writes ABOUT's text into the page: content/about.zh.md and content/about.en.md (at the repository's
root, not published) become static HTML in site/index.html, between its about-switch and about-text
markers. The preview (tools/serve.py) runs it whenever the page is asked for, and the Pages workflow
before it uploads site/, so the published text always follows the files.

The files take a little Markdown only: a blank line starts a paragraph; a lone line break joins the
lines (with no space where either side is Chinese, else with one); **bold**; [words](link), where a
link is http(s)://, mailto: or a section of the page (#projects), the first two opening in a new tab;
a [ that is not a link, and a backslash before * [ ] ( ) or \\, are written as they are. HTML in the files is shown as it is written.
Headings, lists, quotes, images, code and rules stop the build, with the file and the line.

With both files written the section gets a 中 / EN switch; with one, that language alone and no
switch; with neither, the grey bars that stand in for the words.

Usage: python tools/build_about.py [--check]    (--check: only report whether the page is up to date)
"""

import html
import os
import re
import sys
import tempfile
from pathlib import Path

HOME = Path(__file__).resolve().parent.parent
CONTENT = HOME / "content"
PAGE = HOME / "site" / "index.html"
# The languages in the switch's order: (file suffix, lang attribute, the switch's label, what the
# screen reader is told about a link that opens in a new tab)
LANGS = (("zh", "zh-CN", "中", "（在新标签页打开）"), ("en", "en", "EN", " (opens in a new tab)"))
MARKERS = ("about-switch", "about-text")
# Placeholder bars, as the page had them before the words were written
BARS = ('<i class="sk" style="--w: 96%"></i><i class="sk" style="--w: 90%"></i><i class="sk" style="--w: 93%"></i>',
        '<i class="sk" style="--w: 84%"></i><i class="sk" style="--w: 42%"></i>')

# What the files may not hold, as (pattern on a line, what to call it)
UNSUPPORTED = (
    (re.compile(r"^\s{0,3}#{1,6}(\s|$)"), "标题（#）"),
    (re.compile(r"^\s*[-*+]\s"), "列表（- / * / +）"),
    (re.compile(r"^\s*\d+[.)]\s"), "编号列表（1.）"),
    (re.compile(r"^\s*>"), "引用（>）"),
    (re.compile(r"^\s*(```|~~~)"), "代码块（```）"),
    (re.compile(r"^\s*([-*_])(\s*\1){2,}\s*$"), "分隔线（---）"),
    (re.compile(r"^\s*\|"), "表格（|）"),
    (re.compile(r"!\["), "图片（![…](…)）"),
    (re.compile(r"(?<!\\)`"), "行内代码（`）"),
)
# Chinese (and the full-width punctuation round it): no space where a line break joins it to the next
CJK = re.compile(r"[⺀-鿿　-〿豈-﫿︰-﹏＀-￯]")
# (the anchors are the sections main.js knows, TABS; # alone is the opening screen)
LINK = re.compile(r"(?:https?://|mailto:)\S+$|#(?:about|projects|contact|settings)?$")
ESCAPABLE = "*[]()\\"


class AboutError(Exception):
    pass


def _fail(path, number, message):
    name = path.relative_to(HOME).as_posix() if path.is_relative_to(HOME) else path.name
    raise AboutError(f"{name} 第 {number} 行：{message}")


def _join(lines):
    text = ""
    for line in lines:
        if text and not (CJK.match(text[-1]) or CJK.match(line[0])):
            text += " "
        text += line
    return text


def _inline(text, say_new_tab, path, number):
    """One paragraph's text as HTML: the escapes, **bold** and [links](...), everything else escaped."""
    out, i, bold = [], 0, False
    while i < len(text):
        c = text[i]
        if c == "\\" and i + 1 < len(text) and text[i + 1] in ESCAPABLE:
            out.append(html.escape(text[i + 1]))
            i += 2
        elif text.startswith("**", i):
            out.append("</strong>" if bold else "<strong>")
            bold = not bold
            i += 2
        elif c == "[" and (close := _closing(text, i)) >= 0 and text.startswith("(", close + 1) \
                and text.find(")", close + 2) >= 0:
            end = text.find(")", close + 2)
            words, href = text[i + 1:close], text[close + 2:end].strip()
            if not words.strip():
                _fail(path, number, "链接的文字是空的")
            if not LINK.match(href):
                _fail(path, number, f"链接 “{href}” 不支持：只能是 http(s)://、mailto:，或 #、#about、#projects、#contact、#settings")
            inner = _inline(words, say_new_tab, path, number)
            if href.startswith("#"):
                out.append(f'<a href="{html.escape(href)}">{inner}</a>')
            else:
                out.append(f'<a href="{html.escape(href)}" target="_blank" rel="noopener">{inner}'
                           f'<span class="sr-only">{say_new_tab}</span></a>')
            i = end + 1
        else:
            out.append(html.escape(c))
            i += 1
    if bold:
        _fail(path, number, "** 没有成对：加粗要写成 **文字**")
    return "".join(out)


def _closing(text, start):
    """Where the ] closing the [ at start is (escaped brackets skipped), or -1."""
    i = start + 1
    while i < len(text):
        if text[i] == "\\":
            i += 2
            continue
        if text[i] == "]":
            return i
        i += 1
    return -1


def read(path, say_new_tab):
    """The file's paragraphs as HTML ([] where it is missing or has no words)."""
    if not path.is_file():
        return []
    lines = path.read_text(encoding="utf-8-sig").splitlines()
    paragraphs, block, first = [], [], 0
    for number, line in enumerate(lines + [""], 1):
        if line.strip():
            for pattern, name in UNSUPPORTED:
                if pattern.search(line):
                    _fail(path, number, f"ABOUT 不支持{name}，只支持分段、**加粗** 和 [链接](地址)")
            if not block:
                first = number
            block.append(line.strip())
        elif block:
            paragraphs.append(_inline(_join(block), say_new_tab, path, first))
            block = []
    return paragraphs


def render(content=CONTENT):
    """The two regions' HTML, {marker: html}, from the files in content/."""
    written = []
    for suffix, lang, label, say_new_tab in LANGS:
        paragraphs = read(content / f"about.{suffix}.md", say_new_tab)
        if paragraphs:
            written.append((suffix, lang, label, paragraphs))
    if not written:
        return {"about-switch": "", "about-text": "\n".join(BARS)}
    switch = ""
    if len(written) > 1:
        buttons = "\n".join(
            f'  <button type="button" data-lang="{suffix}" lang="{lang}" aria-pressed="{str(i == 0).lower()}">{label}</button>'
            for i, (suffix, lang, label, _) in enumerate(written))
        switch = f'<div class="lang-switch" id="langSwitch" role="group" aria-label="Language">\n{buttons}\n</div>'
    blocks = []
    for i, (suffix, lang, _, paragraphs) in enumerate(written):
        body = "\n".join(f"  <p>{p}</p>" for p in paragraphs)
        blocks.append(f'<div class="about-lang" data-lang="{suffix}" lang="{lang}"{" hidden" if i else ""}>\n{body}\n</div>')
    return {"about-switch": switch, "about-text": "\n".join(blocks)}


def apply(page_text, regions):
    """The page's text with each marked region replaced, kept at the start marker's indentation."""
    newline = "\r\n" if "\r\n" in page_text else "\n"
    for name in MARKERS:
        pattern = re.compile(rf"^([ \t]*)<!-- {name}:start -->.*?^[ \t]*<!-- {name}:end -->", re.M | re.S)
        found = pattern.search(page_text)
        if not found:
            raise AboutError(f"site/index.html 里找不到 <!-- {name}:start --> 和 <!-- {name}:end -->")
        indent = found.group(1)
        inner = "".join(f"{indent}{line}{newline}" for line in regions[name].splitlines())
        block = f"{indent}<!-- {name}:start -->{newline}{inner}{indent}<!-- {name}:end -->"
        page_text = page_text[:found.start()] + block + page_text[found.end():]
    # the placeholder bars say nothing to a screen reader; the words do
    hidden = 'aria-hidden="true"' if "about-lang" not in regions["about-text"] else ""
    page_text = re.sub(r'<div class="about-text"[^>]*>', f'<div class="about-text"{" " + hidden if hidden else ""}>',
                       page_text, count=1)
    return page_text


def build(check=False, page=PAGE, content=CONTENT):
    """Brings the page up to date; True where it changed (or, with check, would change)."""
    with open(page, encoding="utf-8", newline="") as f:
        before = f.read()
    after = apply(before, render(content))
    if after == before:
        return False
    if not check:
        # Written beside the page and moved onto it, so a reader never sees half a page. The name is
        # made here, in the page's own directory, so no caller's path can name the file written.
        handle, temp = tempfile.mkstemp(dir=page.parent, prefix=".about-", suffix=".tmp")
        try:
            with os.fdopen(handle, "w", encoding="utf-8", newline="") as f:
                f.write(after)
            os.replace(temp, page)
        except BaseException:
            try:
                os.unlink(temp)
            except OSError:
                pass
            raise
    return True


def main():
    check = "--check" in sys.argv[1:]
    try:
        changed = build(check)
    except AboutError as error:
        print(f"ABOUT 没有更新：{error}", file=sys.stderr)
        return 1
    if check:
        print("ABOUT 需要更新：请运行 python tools/build_about.py" if changed else "ABOUT 已是最新。")
        return 1 if changed else 0
    print("ABOUT 已写入 site/index.html。" if changed else "ABOUT 已是最新，没有改动。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
