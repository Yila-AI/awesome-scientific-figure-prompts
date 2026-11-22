#!/usr/bin/env python3
"""Build the publishable gallery and 16-language READMEs from prompts/ and records.jsonl.

For every template and language, the first image marked usable is published;
gallery_extra lists further usable attempts to publish as alternates. A
gallery/<theme>/<id>-<lang>.jpg committed by hand is used when that language
has no records. Writes:
  gallery/<theme>/<id>-<lang>[-<attempt>].jpg   compressed images
  gallery/cover.jpg                              3x3 cover of the featured set
  gallery.json                                   machine-readable index
  README.md + 15 localized README_*.md           generated, do not edit by hand

Raw files under images/ are gitignored. When they are absent, existing gallery
JPEGs are kept and Pillow is not required.
"""
import json
import pathlib
import re
import sys
import time
from urllib.parse import quote

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from i18n import LANGUAGES, STRINGS, THEME_NAMES

ROOT = pathlib.Path(__file__).resolve().parent.parent
MODEL_NAME = "GPT Image 2.6"
REPO = "Yila-AI/awesome-scientific-figure-prompts"
REPO_URL = f"https://github.com/{REPO}"
FEATURED_ORDER = ("car-t-solid-tumor", "cgas-sting", "alzheimers-brain", "mouse-model-dosing")
FIGPAD_URL = "https://figpad.ai/?utm_source=github&utm_medium=readme&utm_campaign=sci-figure-prompts"
RELATED_URL = "https://github.com/Yila-AI/awesome-research-skills"
CHECKLIST = "docs/checklist.md"
NEW_PROMPT_ISSUE = f"{REPO_URL}/issues/new?template=new-prompt.yml"
ERROR_ISSUE = f"{REPO_URL}/issues/new?template=scientific-error.yml"
MAX_PER_THEME_IN_README = 8  # 12 disciplines * 8 = 96 prompts (stays safely under GitHub's 512 KB cap in all 16 languages)

THEMES = [
    ("research-design", "🗺️"),
    ("graphical-abstract", "🧭"),
    ("signaling-pathway", "🧬"),
    ("medical-illustration", "🫀"),
    ("experimental-workflow", "🧪"),
    ("materials-energy", "🔋"),
    ("earth-environment", "🌍"),
    ("ai-computing", "🤖"),
    ("engineering-systems", "⚙️"),
    ("chemistry-instruments", "⚗️"),
    ("plant-agriculture", "🌱"),
    ("social-science", "📊"),
]

STYLE_NAMES = {
    "A": ("期刊式扁平矢量", "flat vector schematic"),
    "B": ("柔和半写实插图", "soft semi-realistic illustration"),
    "W": ("扁平流程图", "flat workflow"),
    "D": ("期刊式示意框图", "schematic diagram"),
    "S": ("期刊式科学插画", "scientific illustration"),
}

FEATURED_COVER_TILES = [
    ("wound-healing-stages", "en"), ("liver-fibrosis", "en"), ("nanoparticle-tumor-delivery", "en"),
    ("cgas-sting", "zh"), ("mouse-model-dosing", "zh"), ("alzheimers-brain", "zh"),
    ("fracture-healing", "zh"), ("hydrogel-wound", "en"), ("tgfb-smad", "zh"),
]
EXTRA = [("exercise-glut4", "zh", 2), ("scrna-seq-workflow", "zh", 5)]
STATIC_GALLERY_IMAGES = {"cover.jpg", "banner.jpg", "web-gallery-en.jpg", "web-gallery-zh.jpg"}
PROMO_COUNT = "1000+"
PROMO_REMAINING = "900+"
STATE = {"republished": False}


def load():
    figs = {}
    for p in sorted((ROOT / "prompts").glob("*/*.json")):
        f = json.loads(p.read_text(encoding="utf-8"))
        figs[f["id"]] = f
    rec_path = ROOT / "records.jsonl"
    if rec_path.exists():
        recs = [json.loads(l) for l in rec_path.read_text(encoding="utf-8").splitlines() if l.strip()]
    else:
        recs = []
    styles = json.loads((ROOT / "styles.json").read_text(encoding="utf-8"))
    return figs, recs, styles


def save_jpeg(src, dest):
    from PIL import Image
    dest.parent.mkdir(parents=True, exist_ok=True)
    Image.open(src).convert("RGB").save(dest, "JPEG", quality=86, optimize=True)
    STATE["republished"] = True


def resolve_image(rec, suffix=""):
    """Published gallery path. Encode from images/ when that source exists."""
    out = ROOT / "gallery" / rec["theme"] / f"{rec['id']}-{rec['lang']}{suffix}.jpg"
    src = ROOT / rec["image"]
    if src.exists():
        save_jpeg(src, out)
    elif not out.exists():
        raise SystemExit(f"missing {src} and no published file at {out}")
    return str(out.relative_to(ROOT))


def manual_image(fig, lang):
    path = ROOT / "gallery" / fig["theme"] / f"{fig['id']}-{lang}.jpg"
    if path.exists():
        return str(path.relative_to(ROOT))
    return None


def technique_en(fig):
    text = (fig.get("technique_en") or "").strip()
    if not text:
        raise SystemExit(f"{fig['id']}: add technique_en so English README does not copy Chinese text")
    if re.search(r"[\u4e00-\u9fff]", text):
        raise SystemExit(f"{fig['id']}: technique_en still contains Chinese: {text}")
    return text


def entry_credit(fig):
    featured = bool(fig.get("featured", False))
    added = (fig.get("added") or "").strip()
    if added and not re.fullmatch(r"\d{4}-\d{2}-\d{2}", added):
        raise SystemExit(f"{fig['id']}: added must be YYYY-MM-DD, got {added!r}")
    author = (fig.get("author") or "").strip().lstrip("@")
    author_url = (fig.get("author_url") or "").strip()
    if author_url and not author_url.startswith(("https://", "http://")):
        raise SystemExit(f"{fig['id']}: author_url must be an http(s) URL")
    return featured, added, author, author_url


def build():
    figs, recs, styles = load()
    entries = []
    for theme, _ in THEMES:
        for fid, fig in figs.items():
            if fig["theme"] != theme:
                continue
            mine = [r for r in recs if r["id"] == fid]
            images = []
            for lang in ("en", "zh"):
                ok = [r for r in mine if r["lang"] == lang and r.get("usable")]
                if ok:
                    images.append({"lang": lang, "src": resolve_image(ok[0]), "attempt": ok[0]["attempt"]})
                elif not any(r["lang"] == lang for r in mine):
                    src = manual_image(fig, lang)
                    if src:
                        images.append({"lang": lang, "src": src, "attempt": 1})
            for eid, lang, attempt in EXTRA:
                if eid == fid:
                    rec = next(r for r in mine if r["lang"] == lang and r["attempt"] == attempt)
                    images.append({"lang": lang, "src": resolve_image(rec, f"-{attempt}"), "attempt": attempt})
            if not images:
                raise SystemExit(f"{fid}: no reviewed image. Add gallery/{fig['theme']}/{fid}-en.jpg or mark a record usable.")
            zh_shown = any(i["lang"] == "zh" for i in images)
            zh_rejected = any(r["lang"] == "zh" and r.get("usable") is False for r in mine)
            zh_passed = any(r["lang"] == "zh" and r.get("usable") is True for r in mine)
            featured, added, author, author_url = entry_credit(fig)
            entries.append({
                "id": fid, "theme": theme, "title": fig["title"],
                "technique": fig.get("technique", ""),
                "technique_en": technique_en(fig),
                "featured": featured,
                "added": added,
                "author": author,
                "author_url": author_url,
                "style": fig["style"], "size": fig["size"], "images": images,
                "generations": len(mine),
                "zh_output_failed_review": bool(zh_rejected and not zh_passed and not zh_shown),
                "prompt": {lang: fig["content"][lang].strip() + "\n\n" + styles[fig["style"]][lang].strip()
                           for lang in ("zh", "en")},
            })
    for n, e in enumerate(entries, 1):
        e["no"] = n
    (ROOT / "gallery.json").write_text(json.dumps(entries, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    make_cover(entries)

    updated_date = time.strftime("%Y-%m-%d", time.gmtime())
    updated_iso = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    for code, filename, _, gallery_url, prompt_lang in LANGUAGES:
        content = render(entries, code, gallery_url, prompt_lang, updated_date, updated_iso)
        (ROOT / filename).write_text(content, encoding="utf-8")

    stale = ROOT / "README_en.md"
    if stale.exists():
        stale.unlink()

    problems = verify(entries)
    if problems:
        raise SystemExit("README check failed:\n" + "\n".join(problems))
    total = sum(len(e["images"]) for e in entries)
    print(f"{len(entries)} templates, {total} images, {len(LANGUAGES)} localized READMEs")


def make_cover(entries):
    cover_path = ROOT / "gallery" / "cover.jpg"
    if cover_path.exists() and not STATE["republished"]:
        return
    from PIL import Image
    by = {(e["id"], i["lang"]): i["src"] for e in entries for i in e["images"]}
    tile_w, tile_h, gap = 640, 400, 12
    cover = Image.new("RGB", (tile_w * 3 + gap * 4, tile_h * 3 + gap * 4), "white")
    for k, key in enumerate(FEATURED_COVER_TILES):
        im = Image.open(ROOT / by[key]).convert("RGB")
        im.thumbnail((tile_w, tile_h))
        x = gap + (k % 3) * (tile_w + gap) + (tile_w - im.width) // 2
        y = gap + (k // 3) * (tile_h + gap) + (tile_h - im.height) // 2
        cover.paste(im, (x, y))
    cover_path.parent.mkdir(parents=True, exist_ok=True)
    cover.save(cover_path, "JPEG", quality=86, optimize=True)


def html_attr(text):
    return text.replace("&", "&amp;").replace('"', "&quot;").replace("<", "&lt;")


def badge_escape(text):
    return quote(text.replace("-", "--").replace("_", "__"), safe="")


def utm(base_url, medium, content=None):
    sep = "&" if "?" in base_url else "?"
    url = f"{base_url}{sep}utm_source=github&utm_medium={medium}&utm_campaign=sci-figure-prompts"
    if content:
        url += f"&utm_content={content}"
    return url


def entry_url(gallery_url, entry_id, medium):
    return utm(f"{gallery_url}/{entry_id}", medium, content=entry_id)


def primary_image(entry, pref_lang):
    order = ("zh", "en") if pref_lang == "zh" else ("en", "zh")
    for lang in order:
        for img in entry["images"]:
            if img["lang"] == lang:
                return img["src"]
    return entry["images"][0]["src"]


def lang_switcher(current_code):
    parts = []
    for code, filename, label, _, _ in LANGUAGES:
        enc_label = badge_escape(label)
        if code == current_code:
            badge = f"https://img.shields.io/badge/{enc_label}-Current-brightgreen"
        else:
            badge = f"https://img.shields.io/badge/{enc_label}-Click%20to%20View-lightgrey"
        parts.append(f"[![{label}]({badge})]({filename})")
    return " ".join(parts)


def select_readme_entries(entries):
    """Select up to MAX_PER_THEME_IN_README entries per discipline (featured first)."""
    selected_by_theme = {}
    shown_count = 0
    for theme, _ in THEMES:
        items = [e for e in entries if e["theme"] == theme]
        # Keep featured entries in front so every featured entry is also easy to find
        items_sorted = sorted(items, key=lambda x: (not x.get("featured", False), x["no"]))
        picked = items_sorted[:MAX_PER_THEME_IN_README]
        picked.sort(key=lambda x: x["no"])
        selected_by_theme[theme] = picked
        shown_count += len(picked)
    return selected_by_theme, shown_count


def render_card(e, t, code, gallery_url, prompt_lang, is_featured=False):
    is_zh = prompt_lang == "zh"
    title = e["title"]["zh" if is_zh else "en"]
    theme_label = THEME_NAMES[code][e["theme"]]
    sz, se = STYLE_NAMES[e["style"]]
    style_text = sz if is_zh else se
    technique = e["technique"] if is_zh else e["technique_en"]

    anchor_id = f"featured-no-{e['no']}" if is_featured else f"no-{e['no']}"
    heading_prefix = "###" if is_featured else "####"
    sub_prefix = "####" if is_featured else "#####"
    img_width = 700 if is_featured else 600
    medium = "readme_featured" if is_featured else "readme"

    badges = [
        f"![Model](https://img.shields.io/badge/Model-{badge_escape(MODEL_NAME)}-10a37f)",
        f"![Category](https://img.shields.io/badge/{badge_escape(theme_label)}-blue)",
    ]
    if is_featured or e.get("featured"):
        badges.append("![Featured](https://img.shields.io/badge/%E2%AD%90-Featured-gold)")

    first_lang, second_lang = ("zh", "en") if is_zh else ("en", "zh")
    img_src = primary_image(e, prompt_lang)
    alt = html_attr(title)

    author_str = f"[@{e['author']}]({e['author_url']})" if e.get("author") and e.get("author_url") else (
        f"@{e['author']}" if e.get("author") else "[@Yila-AI](https://github.com/Yila-AI)"
    )

    L = [
        f'<a id="{anchor_id}"></a>',
        "",
        f"{heading_prefix} No. {e['no']}: {title}",
        "",
        " ".join(badges),
        "",
        f"{sub_prefix} 📖 {t['lbl_desc']}",
        "",
        f"{t['technique_prefix']}: **{technique}** · {t['lbl_style']}: {style_text} · {t['lbl_ratio']}: `{e['size']}`",
        "",
        f"{sub_prefix} 📝 {t['lbl_prompt']}",
        "",
        "```text",
        e["prompt"][first_lang],
        "```",
        "",
        f"<details><summary>{t['lbl_alt_prompt']}</summary>",
        "",
        "```text",
        e["prompt"][second_lang],
        "```",
        "",
        "</details>",
        "",
        f"{sub_prefix} 🖼️ {t['lbl_images']}",
        "",
        '<div align="center">',
        f'<a href="{entry_url(gallery_url, e["id"], medium)}"><img src="{img_src}" width="{img_width}" alt="{alt}"></a>',
        "</div>",
        "",
        f"{sub_prefix} 📌 {t['lbl_details']}",
        "",
        f"- **{t['lbl_author']}:** {author_str}",
        f"- **{t['lbl_model']}:** {MODEL_NAME}",
        f"- **{t['lbl_ratio']}:** {e['size']}",
        f"- **{t['lbl_langs']}:** en, zh",
        "",
        f"**[👉 {t['cta_try']}]({entry_url(gallery_url, e['id'], medium)})** · [{t['back_top']}](#top)",
        "",
        "---",
        "",
    ]
    return L


def render(entries, code, gallery_url, prompt_lang, updated_date, updated_iso):
    t = STRINGS[code]
    n = len(entries)
    total_images = sum(len(e["images"]) for e in entries)
    featured_entries = [e for e in entries if e.get("featured")]
    by_id = {e["id"]: e for e in featured_entries}
    featured_ordered = [by_id[i] for i in FEATURED_ORDER if i in by_id]
    featured_ordered += [e for e in featured_entries if e["id"] not in FEATURED_ORDER]

    selected_by_theme, shown_count = select_readme_entries(entries)
    remaining = PROMO_REMAINING
    gallery_cover = "gallery/web-gallery-zh.jpg" if prompt_lang == "zh" else "gallery/web-gallery-en.jpg"

    L = [
        "<!-- Generated by tools/build_gallery.py. Do not edit by hand. -->",
        "",
        '<a id="top"></a>',
        "",
        f'<a href="{utm(gallery_url, "readme_banner")}">',
        f'  <img src="gallery/banner.jpg" alt="{html_attr(t["banner_alt"])}" width="100%" />',
        "</a>",
        "",
        f'> 💡 🔬 {t["callout"].format(n="1000")} [{t["callout_link"]}]({utm(gallery_url, "readme_callout")})',
        "",
        f"# 🔬 {t['title']}",
        "",
        "[![Awesome](https://awesome.re/badge.svg)](https://github.com/sindresorhus/awesome)",
        f"[![GitHub stars](https://img.shields.io/github/stars/{REPO}?style=social)]({REPO_URL})",
        "![Templates](https://img.shields.io/badge/templates-1000%2B-blue)",
        "[![License: CC BY 4.0](https://img.shields.io/badge/License-CC%20BY%204.0-lightgrey.svg)](LICENSE)",
        f"[![Verify README]({REPO_URL}/actions/workflows/check-readme.yml/badge.svg)]({REPO_URL}/actions)",
        "[![PRs Welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg)](CONTRIBUTING.md)",
        "",
        f"> 🎨 {t['tagline']}",
        "",
        f"> ⚠️ **{t['notice_label']}**: {t['notice_body'].format(error_issue=ERROR_ISSUE)}",
        "",
        "---",
        "",
        lang_switcher(code),
        "",
        "---",
        "",
        '<a id="web-gallery"></a>',
        "",
        f"## 🌐 {t['sec_gallery']}",
        "",
        '<div align="center">',
        "",
        f'<a href="{utm(gallery_url, "readme_cover")}">',
        f'  <img src="{gallery_cover}" alt="{html_attr(t["banner_alt"])}" width="100%" />',
        "</a>",
        "",
        "</div>",
        "",
        f"**[👉 {t['cta_browse']}]({utm(gallery_url, 'readme_gallery')})**",
        "",
        t["why_gallery"],
        "",
        f"| {t['tbl_feature']} | {t['tbl_github']} | {t['tbl_web']} |",
        "|---------|--------------|---------------------|",
    ]
    for feat, gh_col, web_col in t["rows"]:
        L.append(f"| {feat} | {gh_col} | {web_col} |")

    L += [
        "",
        f"### 🏷️ {t['sec_categories']}",
        "",
    ]
    for theme, emoji in THEMES:
        count = sum(1 for e in entries if e["theme"] == theme)
        tname = THEME_NAMES[code][theme]
        cat_url = utm(f"{gallery_url}?theme={theme}", "readme_category", content=theme)
        L.append(f"- {emoji} **[{tname}]({cat_url})** ({count} {t['tpl_unit']})")

    L += [
        "",
        "---",
        "",
        f"## 📖 {t['sec_toc']}",
        "",
        f"- [🌐 {t['sec_gallery']}](#web-gallery)",
        f"- [🤔 {t['sec_what_is']}](#what-is-gpt-image-26)",
        f"- [📊 {t['sec_stats']}](#statistics)",
        f"- [🔥 {t['sec_featured']}](#featured-prompts)",
        f"- [📋 {t['sec_all']}](#all-prompts)",
        f"- [🤝 {t['sec_contribute']}](#how-to-contribute)",
        f"- [📄 {t['sec_license']}](#license)",
        f"- [🙏 {t['sec_ack']}](#acknowledgements)",
        f"- [⭐ {t['sec_star']}](#star-history)",
        "",
        "---",
        "",
        '<a id="what-is-gpt-image-26"></a>',
        "",
        f"## 🤔 {t['sec_what_is']}",
        "",
        t["what_is_intro"],
        "",
    ]
    for bullet in t["what_is_bullets"]:
        L.append(f"- {bullet}")

    L += [
        "",
        f"### 🛠️ {t['sec_howto']}",
        "",
    ]
    for idx, step in enumerate(t["howto_steps"], 1):
        L.append(f"{idx}. {step}")

    L += [
        "",
        f"> 💡 {t['howto_tip'].format(url=utm(gallery_url, 'readme_howto'))}",
        "",
        f"**{t['related_label']}** [awesome-research-skills]({RELATED_URL}) — {t['related_desc']}",
        "",
        "---",
        "",
        '<a id="statistics"></a>',
        "",
        f"## 📊 {t['sec_stats']}",
        "",
        '<div align="center">',
        "",
        f"| {t['stat_metric']} | {t['stat_count']} |",
        "|--------|-------|",
        f"| {t['stat_total']} | **{PROMO_COUNT}** |",
        f"| {t['stat_images']} | **{PROMO_COUNT}** |",
        f"| {t['stat_featured']} | **{len(featured_ordered)}** |",
        f"| {t['stat_disciplines']} | **{len(THEMES)}** |",
        f"| {t['stat_model']} | **{MODEL_NAME}** |",
        f"| {t['stat_updated']} | **{updated_date}** |",
        "",
        "</div>",
        "",
        "---",
        "",
        '<a id="featured-prompts"></a>',
        "",
        f"## 🔥 {t['sec_featured']}",
        "",
        f"> ⭐ {t['featured_sub']}",
        "",
    ]

    for e in featured_ordered:
        L += render_card(e, t, code, gallery_url, prompt_lang, is_featured=True)

    L += [
        '<a id="all-prompts"></a>',
        "",
        f"## 📋 {t['sec_all']}",
        "",
    ]

    for theme, emoji in THEMES:
        tname = THEME_NAMES[code][theme]
        L += [
            f'<a id="{theme}"></a>',
            "",
            f"### {emoji} {tname}",
            "",
        ]
        for e in selected_by_theme[theme]:
            L += render_card(e, t, code, gallery_url, prompt_lang, is_featured=False)

    L += [
        f"## 📚 {t['sec_more']}",
        "",
        '<div align="center">',
        "",
        f"### 🎯 {t['more_heading'].format(rem=remaining)}",
        "",
        t["more_desc"].format(shown=shown_count),
        "",
        f"**[👉 {t['cta_view_all'].format(n=PROMO_COUNT)}]({utm(gallery_url, 'readme_more')})**",
        "",
    ]
    for b in t["more_bullets"]:
        L += [b, ""]
    L += ["</div>", "", "---", ""]

    L += [
        '<a id="how-to-contribute"></a>',
        "",
        f"## 🤝 {t['sec_contribute']}",
        "",
        t["contrib_intro"],
        "",
    ]
    for idx, step in enumerate(t["contrib_steps"], 1):
        L.append(f"{idx}. {step.format(new_issue=NEW_PROMPT_ISSUE, err_issue=ERROR_ISSUE)}")

    L += [
        "",
        t["contrib_guide"],
        "",
        "---",
        "",
        '<a id="license"></a>',
        "",
        f"## 📄 {t['sec_license']}",
        "",
        t["license_text"],
        "",
        "---",
        "",
        '<a id="acknowledgements"></a>',
        "",
        f"## 🙏 {t['sec_ack']}",
        "",
        f"- **[YILA AI]({utm(gallery_url, 'readme_footer')})** — {t['ack_yila']}",
        f"- **[FigPad]({FIGPAD_URL})** — {t['ack_figpad']}",
        f"- **[awesome-research-skills]({RELATED_URL})** — {t['ack_skills']}",
        "",
        "---",
        "",
        '<a id="star-history"></a>',
        "",
        f"## ⭐ {t['sec_star']}",
        "",
        f"[![Star History Chart](https://api.star-history.com/svg?repos={REPO}&type=Date)](https://star-history.com/#{REPO}&Date)",
        "",
        "---",
        "",
        '<div align="center">',
        "",
        f"**[🌐 {t['footer_gallery']}]({utm(gallery_url, 'readme_bottom')})** •",
        f"**[📝 {t['footer_submit']}]({NEW_PROMPT_ISSUE})** •",
        f"**[⭐ {t['footer_star']}]({REPO_URL})**",
        "",
        f"<sub>🤖 {t['footer_auto'].format(ts=updated_iso)}</sub>",
        "",
        "</div>",
        "",
    ]
    return "\n".join(L).rstrip() + "\n"


def verify(entries):
    problems = []
    published = {i["src"] for e in entries for i in e["images"]}
    on_disk = {
        str(p.relative_to(ROOT))
        for p in (ROOT / "gallery").rglob("*.jpg")
        if p.name not in STATIC_GALLERY_IMAGES
    }
    if published != on_disk:
        problems.append(f"gallery index {sorted(published - on_disk)} vs disk {sorted(on_disk - published)}")
    for static_img in ("gallery/cover.jpg", "gallery/banner.jpg", "gallery/web-gallery-en.jpg", "gallery/web-gallery-zh.jpg"):
        if not (ROOT / static_img).exists():
            problems.append(f"missing {static_img}")

    if (ROOT / "README_en.md").exists():
        problems.append("README_en.md should not exist; English is README.md")

    required_section_ids = [
        "top", "web-gallery", "what-is-gpt-image-26", "statistics",
        "featured-prompts", "all-prompts", "how-to-contribute",
        "license", "acknowledgements", "star-history",
        *(theme for theme, _ in THEMES),
    ]

    for code, filename, label, gallery_url, _ in LANGUAGES:
        path = ROOT / filename
        if not path.exists():
            problems.append(f"missing {filename}")
            continue
        raw = path.read_bytes()
        if len(raw) >= 500_000:
            problems.append(f"{filename}: size {len(raw)} bytes approaches GitHub 512 KB truncation limit")
        text = raw.decode("utf-8")
        ids = set(re.findall(r'<a id="([^"]+)"></a>', text))
        for anchor in required_section_ids:
            if anchor not in ids:
                problems.append(f"{filename}: missing anchor #{anchor}")
        for href in re.findall(r'\(#([A-Za-z0-9-]+)\)', text):
            if href not in ids:
                problems.append(f"{filename}: link #{href} has no anchor")
        for href in re.findall(r'href="#([^"]+)"', text):
            if href not in ids:
                problems.append(f"{filename}: href #{href} has no anchor")
        for src in re.findall(r'src="(gallery/[^"]+)"', text):
            if not (ROOT / src).exists():
                problems.append(f"{filename}: missing image {src}")
        for rel in re.findall(r'\]\((?!https?:|#)([^)]+)\)', text):
            rel_path = rel.split("#", 1)[0]
            if rel_path and not (ROOT / rel_path).exists():
                problems.append(f"{filename}: missing link target {rel_path}")
        if "templates-1000%2B-blue" not in text:
            problems.append(f"{filename}: template badge count is not 1000+")
        if gallery_url not in text:
            problems.append(f"{filename}: missing gallery url {gallery_url}")
        if MODEL_NAME not in text:
            problems.append(f"{filename}: missing model name {MODEL_NAME}")
        if "Nano Banana" in text or "gemini-3.1-flash-lite-image" in text:
            problems.append(f"{filename}: stale model reference still present")
        if f"{badge_escape(label)}-Current-brightgreen" not in text:
            problems.append(f"{filename}: current language badge not highlighted")

    saved = json.loads((ROOT / "gallery.json").read_text(encoding="utf-8"))
    if [e["id"] for e in saved] != [e["id"] for e in entries]:
        problems.append("gallery.json entries do not match the generated index")
    return problems


if __name__ == "__main__":
    build()
