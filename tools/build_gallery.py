#!/usr/bin/env python3
"""Build the publishable gallery from prompts/ and records.jsonl.

For every template and language, the first image marked usable is published;
gallery_extra lists further usable attempts to publish as alternates. A
gallery/<theme>/<id>-<lang>.jpg committed by hand is used when that language
has no records (so a Gemini or ChatGPT UI export is enough). Writes:
  gallery/<theme>/<id>-<lang>[-<attempt>].jpg   compressed images
  gallery/cover.jpg                              3x3 cover of the featured set
  gallery.json                                   machine-readable index
  README.md / README_en.md                       generated, do not edit by hand

Raw files under images/ are gitignored. When they are absent, existing gallery
JPEGs are kept and Pillow is not required.
"""
import json
import pathlib
import re
import time

ROOT = pathlib.Path(__file__).resolve().parent.parent
MODEL_NAME = "Nano Banana 2 Lite (gemini-3.1-flash-lite-image, 1K)"
REPO = "Yila-AI/awesome-scientific-figure-prompts"
REPO_URL = f"https://github.com/{REPO}"
YILA_HOWTO = "https://yila.ai/?utm_source=github&utm_medium=readme_howto&utm_campaign=sci-figure-prompts"
YILA_FOOTER = "https://yila.ai/?utm_source=github&utm_medium=readme_footer&utm_campaign=sci-figure-prompts"
YILA_ENTRY = "https://yila.ai/?utm_source=github&utm_medium=readme&utm_campaign=sci-figure-prompts&utm_content={id}"
FEATURED_ORDER = ("car-t-solid-tumor", "cgas-sting", "alzheimers-brain", "mouse-model-dosing")
FIGPAD_URL = "https://figpad.ai/?utm_source=github&utm_medium=readme&utm_campaign=sci-figure-prompts"
RELATED_URL = "https://github.com/Yila-AI/awesome-research-skills"
CHECKLIST = "docs/checklist.md"
NEW_PROMPT_ISSUE = f"{REPO_URL}/issues/new?template=new-prompt.yml"
ERROR_ISSUE = f"{REPO_URL}/issues/new?template=scientific-error.yml"
REPO_TITLE = "Awesome Scientific Figure Prompts"

THEMES = [
    ("graphical-abstract", "图形摘要", "Graphical Abstract"),
    ("signaling-pathway", "信号通路", "Signaling Pathway"),
    ("medical-illustration", "医学插图", "Medical Illustration"),
    ("experimental-workflow", "实验流程", "Experimental Workflow"),
]
THUMB_EMOJI = {
    "graphical-abstract": "🧭",
    "signaling-pathway": "🧬",
    "medical-illustration": "🫀",
    "experimental-workflow": "🧪",
}
# First-screen thumbnails. Paths are checked at build time.
THUMB_SRC = {
    "graphical-abstract": "gallery/graphical-abstract/nanoparticle-tumor-delivery-en.jpg",
    "signaling-pathway": "gallery/signaling-pathway/cgas-sting-en.jpg",
    "medical-illustration": "gallery/medical-illustration/alzheimers-brain-en.jpg",
    "experimental-workflow": "gallery/experimental-workflow/mouse-model-dosing-en.jpg",
}
COVER_ALT = {
    "en": "AI-generated scientific figures: graphical abstract, cGAS-STING signaling pathway, Alzheimer's brain, fracture healing, mouse experimental workflow",
    "zh": "AI 生成的科研插图：图形摘要、cGAS–STING 信号通路、阿尔茨海默病大脑、骨折愈合、小鼠实验流程",
}
STYLE_NAMES = {"A": ("期刊式扁平矢量", "flat vector schematic"),
               "B": ("柔和半写实插图", "soft semi-realistic illustration"),
               "W": ("扁平流程图", "flat workflow")}
FEATURED = [("wound-healing-stages", "en"), ("liver-fibrosis", "en"), ("nanoparticle-tumor-delivery", "en"),
            ("cgas-sting", "zh"), ("mouse-model-dosing", "zh"), ("alzheimers-brain", "zh"),
            ("fracture-healing", "zh"), ("hydrogel-wound", "en"), ("tgfb-smad", "zh")]
EXTRA = [("exercise-glut4", "zh", 2), ("scrna-seq-workflow", "zh", 5)]
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
        raise SystemExit(f"{fig['id']}: add technique_en so README_en.md does not copy the Chinese technique")
    if re.search(r"[\u4e00-\u9fff]", text):
        raise SystemExit(f"{fig['id']}: technique_en still contains Chinese: {text}")
    return text


def entry_credit(fig):
    """Optional prompt fields copied into gallery.json. Empty strings stay empty."""
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
    for theme, _, _ in THEMES:
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
    for lang in ("zh", "en"):
        name = "README.md" if lang == "zh" else "README_en.md"
        (ROOT / name).write_text(render(entries, lang), encoding="utf-8")
    problems = verify(entries)
    if problems:
        raise SystemExit("README check failed:\n" + "\n".join(problems))
    total = sum(len(e["images"]) for e in entries)
    print(f"{len(entries)} templates, {total} images")


def make_cover(entries):
    cover_path = ROOT / "gallery" / "cover.jpg"
    if cover_path.exists() and not STATE["republished"]:
        return
    from PIL import Image
    by = {(e["id"], i["lang"]): i["src"] for e in entries for i in e["images"]}
    tile_w, tile_h, gap = 640, 400, 12
    cover = Image.new("RGB", (tile_w * 3 + gap * 4, tile_h * 3 + gap * 4), "white")
    for k, key in enumerate(FEATURED):
        im = Image.open(ROOT / by[key]).convert("RGB")
        im.thumbnail((tile_w, tile_h))
        x = gap + (k % 3) * (tile_w + gap) + (tile_w - im.width) // 2
        y = gap + (k // 3) * (tile_h + gap) + (tile_h - im.height) // 2
        cover.paste(im, (x, y))
    cover_path.parent.mkdir(parents=True, exist_ok=True)
    cover.save(cover_path, "JPEG", quality=86, optimize=True)


def html_attr(text):
    return text.replace("&", "&amp;").replace('"', "&quot;").replace("<", "&lt;")


def thumb_title(entries, src, lang):
    name = pathlib.Path(src).name
    for e in entries:
        if name == f"{e['id']}-{lang}.jpg" or name == f"{e['id']}-en.jpg" or name == f"{e['id']}-zh.jpg":
            return e["title"][lang]
    raise SystemExit(f"no entry title for thumbnail {src}")


def summary_line(entries, lang):
    n = len(entries)
    total = sum(len(e["images"]) for e in entries)
    today = time.strftime("%Y-%m-%d")
    if lang == "zh":
        return f"{n} 个模板 · {total} 张示例图 · {MODEL_NAME} · 更新于 {today}"
    return f"{n} templates · {total} example images · {MODEL_NAME} · updated {today}"


def render(entries, lang):
    zh = lang == "zh"
    L = ["<!-- Generated by tools/build_gallery.py. Do not edit by hand. -->", "",
         '<a id="top"></a>', ""]
    L += hero(entries, lang)
    L += featured_grid(entries, lang)
    L += browse(entries, lang)
    L += howto(lang)
    L += ["", summary_line(entries, lang), ""]
    L += contents_list(entries, lang)
    for theme, tzh, ten in THEMES:
        L += theme_section(entries, theme, tzh if zh else ten, lang)
    L += closing(entries, lang)
    return "\n".join(L).rstrip() + "\n"


def hero(entries, lang):
    zh = lang == "zh"
    n = len(entries)
    total = sum(len(e["images"]) for e in entries)
    if zh:
        value = "**5 分钟做出期刊风格的科研图初稿——不用 BioRender，也不用会画画。**"
        keywords = ("可直接复制的提示词模板，覆盖图形摘要、信号通路、医学插图和实验流程，"
                    "每条都用真实的 Nano Banana / Gemini 出图检验过。")
        switch = [
            "[![English](https://img.shields.io/badge/English-View-orange)](README_en.md)",
            "[![简体中文](https://img.shields.io/badge/简体中文-当前-brightgreen)](README.md)",
        ]
    else:
        value = "**Turn your research into a journal-style figure draft in 5 minutes — no BioRender, no drawing skills.**"
        keywords = ("Copy-paste prompt templates for graphical abstracts, signaling pathways, "
                    "medical illustrations and experimental workflows, each tested with real "
                    "Nano Banana / Gemini outputs.")
        switch = [
            "[![English](https://img.shields.io/badge/English-Current-brightgreen)](README_en.md)",
            "[![简体中文](https://img.shields.io/badge/简体中文-点击查看-orange)](README.md)",
        ]
    badges = [
        f"[![GitHub stars](https://img.shields.io/github/stars/{REPO}?style=social)]({REPO_URL})",
        f"![Templates](https://img.shields.io/badge/templates-{n}-blue)",
        f"![Examples](https://img.shields.io/badge/example_images-{total}-blue)",
        "[![License: CC BY 4.0](https://img.shields.io/badge/License-CC%20BY%204.0-lightgrey.svg)](LICENSE)",
        "[![PRs Welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg)](CONTRIBUTING.md)",
    ]
    alt = html_attr(COVER_ALT[lang])
    return [
        '<div align="center">',
        "",
        f"# 🔬 {REPO_TITLE}",
        "",
        value,
        keywords,
        "",
        *badges,
        "",
        *switch,
        "",
        f'<img src="gallery/cover.jpg" alt="{alt}" width="900">',
        "",
        "</div>",
        "",
    ]


def primary_src(entry):
    for lang in ("en", "zh"):
        for image in entry["images"]:
            if image["lang"] == lang:
                return image["src"]
    return entry["images"][0]["src"]


def featured_grid(entries, lang):
    picked = [e for e in entries if e.get("featured")]
    if not picked:
        return []
    by_id = {e["id"]: e for e in picked}
    ordered = [by_id[i] for i in FEATURED_ORDER if i in by_id]
    ordered += [e for e in picked if e["id"] not in FEATURED_ORDER]
    cells = []
    for e in ordered:
        src = primary_src(e)
        alt = html_attr(e["title"][lang])
        title = e["title"][lang]
        cells.append(
            "<td align=\"center\">"
            f'<a href="#no-{e["no"]}"><img src="{src}" alt="{alt}" width="420"></a><br>'
            f'<a href="#no-{e["no"]}">{title}</a>'
            "</td>"
        )
    rows = []
    for i in range(0, len(cells), 2):
        pair = cells[i:i + 2]
        rows.append("<tr>" + "".join(pair) + "</tr>")
    return [
        "## ⭐ 精选 / Featured",
        "",
        "<table>",
        *rows,
        "</table>",
        "",
    ]


def browse(entries, lang):
    zh = lang == "zh"
    headers, thumbs, counts = [], [], []
    for theme, tzh, ten in THEMES:
        name = tzh if zh else ten
        src = THUMB_SRC[theme]
        alt = html_attr(thumb_title(entries, src, lang))
        n = sum(1 for e in entries if e["theme"] == theme)
        headers.append(f"[{THUMB_EMOJI[theme]} {name}](#{theme})")
        thumbs.append(f'<a href="#{theme}"><img src="{src}" alt="{alt}" width="200"></a>')
        counts.append(f"{n} 个模板" if zh else (f"{n} template" if n == 1 else f"{n} templates"))
    return [
        "## " + ("按图类型浏览" if zh else "Browse by figure type"),
        "",
        "| " + " | ".join(headers) + " |",
        "|:-:|:-:|:-:|:-:|",
        "| " + " | ".join(thumbs) + " |",
        "| " + " | ".join(counts) + " |",
        "",
    ]


def howto(lang):
    zh = lang == "zh"
    L = ["## " + ("怎么用" if zh else "How to use"), ""]
    if zh:
        L += [
            "1. 选最接近的模板，复制提示词。",
            "2. 把【】里的内容换成你自己的课题，然后删掉【】。风格段落保持原样。",
            "3. 粘贴到 Gemini、ChatGPT 或任何图像模型。图中文字用英文短标签，出错最少。",
            f"4. 核对箭头、结构位置和拼写。这些是初稿，还不能直接投稿。请先看[投稿前核对清单]({CHECKLIST})。",
            "",
            f"> 💡 不想自己填模板？把论文摘要贴进 [Yila]({YILA_HOWTO})。Yila 是一个科研助手，会选模板、写提示词，并画出初稿。",
            "",
            f"**相关：** [awesome-research-skills]({RELATED_URL})：文献调研、写作和数据分析的 agent skills。",
        ]
    else:
        L += [
            "1. Pick the closest template and copy its prompt.",
            "2. Replace everything inside 【】 with your own topic, then delete the 【】 marks. Keep the style paragraph as is.",
            "3. Paste into Gemini, ChatGPT or any image model. Short English labels give the fewest text errors.",
            "4. Always check arrows, structure positions and spelling. These are first drafts, not submission-ready figures. "
            f"Use the [pre-submission checklist]({CHECKLIST}).",
            "",
            f"> 💡 Don't want to fill templates by hand? Paste your abstract into [Yila]({YILA_HOWTO}), "
            "a research agent that picks a template, writes the prompt and draws the draft for you.",
            "",
            f"**Related:** [awesome-research-skills]({RELATED_URL}): agent skills for literature review, writing and data analysis.",
        ]
    return L


def contents_list(entries, lang):
    zh = lang == "zh"
    L = ["## " + ("目录" if zh else "Contents"), ""]
    for theme, tzh, ten in THEMES:
        items = [e for e in entries if e["theme"] == theme]
        name = tzh if zh else ten
        head = f"**{name}**：" if zh else f"**{name}**: "
        joiner = "、" if zh else ", "
        links = joiner.join(f"[No. {e['no']} {e['title'][lang]}](#no-{e['no']})" for e in items)
        L.append(f"- {head}{links}")
    L.append("")
    return L


def theme_section(entries, theme, heading, lang):
    zh = lang == "zh"
    L = [f'<a id="{theme}"></a>', "", f"## {heading}", ""]
    for e in [e for e in entries if e["theme"] == theme]:
        L += entry_block(e, lang)
    return L


def entry_block(e, lang):
    zh = lang == "zh"
    colon = "：" if zh else ": "
    sz, se = STYLE_NAMES[e["style"]]
    if zh:
        meta = f"写法技巧：**{e['technique']}**　·　风格：{sz}　·　比例：{e['size']}"
    else:
        meta = f"Technique: **{e['technique_en']}** · Style: {se} · Aspect ratio: {e['size']}"
    heads = [("英文提示词出图" if i["lang"] == "en" else "中文提示词出图") if zh else
             ("English prompt" if i["lang"] == "en" else "Chinese prompt") for i in e["images"]]
    L = [f'<a id="no-{e["no"]}"></a>', "", f"### No. {e['no']}{colon}{e['title'][lang]}", ""]
    if e.get("author"):
        handle = e["author"].lstrip("@")
        if e.get("author_url"):
            L += [f"by [@{handle}]({e['author_url']})", ""]
        else:
            L += [f"by @{handle}", ""]
    L += [meta, ""]
    L += [
         "| " + " | ".join(heads) + " |", "|" + "---|" * len(e["images"]),
         "| " + " | ".join(f'<img src="{i["src"]}" width="420">' for i in e["images"]) + " |", ""]
    if e.get("zh_output_failed_review"):
        note = ("中文提示词出图未通过核对，因此这里不展示。" if zh else
                "The Chinese-prompt output did not pass review, so it is not shown.")
        L += [f"> {note}", ""]
    first, second = (("zh", "en") if zh else ("en", "zh"))
    label = {"zh": "中文提示词" if zh else "Chinese prompt", "en": "English prompt"}
    L += [f"**{label[first]}**", "", "```text", e["prompt"][first], "```", ""]
    L += [f"<details><summary>{label[second]}</summary>", "", "```text", e["prompt"][second], "```", "", "</details>", ""]
    if zh:
        if e["generations"]:
            model = f"模型：{MODEL_NAME}　·　这条提示词共生成 {e['generations']} 次，展示的是核对通过的结果"
        else:
            model = f"模型：由投稿者提供示例图　·　风格参考 {MODEL_NAME}"
    else:
        if e["generations"]:
            model = (f"Model: {MODEL_NAME} · Generated {e['generations']} times in total; "
                     "shown are the outputs that passed review")
        else:
            model = f"Model: example image supplied by the contributor · style reference {MODEL_NAME}"
    back = "[↑ 回到顶部](#top)" if zh else "[↑ Back to top](#top)"
    try_label = "用 Yila 试试 →" if zh else "Try in Yila →"
    try_link = f'<sub><a href="{YILA_ENTRY.format(id=e["id"])}">{try_label}</a></sub>'
    L += [model, "", back, "", try_link, "", "---", ""]
    return L


def closing(entries, lang):
    zh = lang == "zh"
    if zh:
        return [
            "## 投稿",
            "",
            "欢迎通过 Pull Request 或 Issue 提交提示词和出图，收录后会署名。"
            f"步骤见 [CONTRIBUTING.md](CONTRIBUTING.md)。也可以直接开 [新提示词]({NEW_PROMPT_ISSUE}) 或 [科学错误]({ERROR_ISSUE})。",
            "",
            "## 许可",
            "",
            "提示词以 [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/) 发布。示例图由 AI 生成，带有模型自带的 SynthID 水印。",
            "",
            "---",
            "",
            f"由 [Yila-AI]({YILA_FOOTER}) 制作。",
            "",
            f"初稿如果还要调整标签、箭头或版式，可以用 [FigPad]({FIGPAD_URL}) 做后期编辑。",
            "",
        ]
    return [
        "## Contributing",
        "",
        "Submit a prompt and its output through a pull request or an issue; accepted entries are credited. "
        f"See [CONTRIBUTING.md](CONTRIBUTING.md), or open a [new prompt]({NEW_PROMPT_ISSUE}) or a [scientific error]({ERROR_ISSUE}).",
        "",
        "## License",
        "",
        "Prompts are released under [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/). "
        "Example images are AI-generated and carry the model's SynthID watermark.",
        "",
        "---",
        "",
        f"Made by [Yila-AI]({YILA_FOOTER}).",
        "",
        f"To adjust labels, arrows, or layout after the draft, edit the figure in [FigPad]({FIGPAD_URL}).",
        "",
    ]


def verify(entries):
    problems = []
    total = sum(len(e["images"]) for e in entries)
    published = {i["src"] for e in entries for i in e["images"]}
    on_disk = {str(p.relative_to(ROOT)) for p in (ROOT / "gallery").rglob("*.jpg") if p.name != "cover.jpg"}
    if published != on_disk:
        problems.append(f"gallery index {sorted(published - on_disk)} vs disk {sorted(on_disk - published)}")
    for src in list(THUMB_SRC.values()) + ["gallery/cover.jpg"]:
        if not (ROOT / src).exists():
            problems.append(f"missing {src}")
    required_ids = ["top", *(theme for theme, _, _ in THEMES), *(f"no-{e['no']}" for e in entries)]
    for lang, filename in (("en", "README_en.md"), ("zh", "README.md")):
        text = (ROOT / filename).read_text(encoding="utf-8")
        ids = set(re.findall(r'<a id="([^"]+)"></a>', text))
        for anchor in required_ids:
            if anchor not in ids:
                problems.append(f"{filename}: missing anchor #{anchor}")
        for href in re.findall(r'\(#([A-Za-z0-9-]+)\)', text):
            if href not in ids:
                problems.append(f"{filename}: link #{href} has no anchor")
        for src in re.findall(r'(?:src|href)="(gallery/[^"]+)"', text):
            if not (ROOT / src).exists():
                problems.append(f"{filename}: missing image {src}")
        for rel in re.findall(r'\]\((?!https?:|#)([^)]+)\)', text):
            path = rel.split("#", 1)[0]
            if path and not (ROOT / path).exists():
                problems.append(f"{filename}: missing link target {path}")
        if f"templates-{len(entries)}-blue" not in text:
            problems.append(f"{filename}: template badge count is not {len(entries)}")
        if f"example_images-{total}-blue" not in text:
            problems.append(f"{filename}: example badge count is not {total}")
        if "shields.io/badge/Awesome" in text or "awesome-list" in text:
            problems.append(f"{filename}: unexpected Awesome badge")
        if text.count("utm_medium=readme_howto") != 1:
            problems.append(f"{filename}: howto utm count {text.count('utm_medium=readme_howto')}")
        if text.count("utm_medium=readme_footer") != 1:
            problems.append(f"{filename}: footer utm count {text.count('utm_medium=readme_footer')}")
        if "utm_medium=referral" in text:
            problems.append(f"{filename}: old referral utm still present")
        if text.count("figpad.ai") != 1:
            problems.append(f"{filename}: FigPad mentions = {text.count('figpad.ai')}")
        if text.count("[↑") != len(entries):
            problems.append(f"{filename}: back-to-top count {text.count('[↑')}")
        if CHECKLIST not in text:
            problems.append(f"{filename}: checklist not linked")
        if "## Statistics" in text or "## 统计" in text or "| Templates |" in text or "| 模板 |" in text:
            problems.append(f"{filename}: stats table still present")
        howto_heading = "## How to use" if lang == "en" else "## 怎么用"
        line = summary_line(entries, lang)
        if line not in text:
            problems.append(f"{filename}: missing one-line summary")
        elif text.find(howto_heading) > text.find(line):
            problems.append(f"{filename}: summary is above how-to")
        for e in entries:
            if not e.get("zh_output_failed_review"):
                continue
            start = text.find(f'id="no-{e["no"]}"')
            nxt = text.find(f'id="no-{e["no"] + 1}"')
            chunk = text[start: nxt if nxt != -1 else len(text)]
            phrase = "did not pass review" if lang == "en" else "未通过核对"
            if phrase not in chunk:
                problems.append(f"{filename}: No. {e['no']} missing review note")
            if any(i["lang"] == "zh" for i in e["images"]):
                problems.append(f"{filename}: No. {e['no']} shows a Chinese-prompt image")
        if "⭐ 精选 / Featured" not in text:
            problems.append(f"{filename}: missing featured heading")
        elif text.find("⭐ 精选 / Featured") > text.find(howto_heading):
            problems.append(f"{filename}: featured section is below how-to")
        featured_ids = [e["id"] for e in entries if e.get("featured")]
        if featured_ids != list(FEATURED_ORDER):
            problems.append(f"{filename}: featured ids {featured_ids}")
        for e in entries:
            token = f"utm_content={e['id']}"
            if text.count(token) != 1:
                problems.append(f"{filename}: {token} count {text.count(token)}")
            if e.get("author") and f"by [@{e['author'].lstrip('@')}]" not in text and f"by @{e['author'].lstrip('@')}" not in text:
                problems.append(f"{filename}: missing credit for {e['id']}")
            if e.get("featured"):
                src = primary_src(e)
                if f'<a href="#no-{e["no"]}"><img src="{src}"' not in text:
                    problems.append(f"{filename}: featured image for {e['id']} is not linked")
        for href in re.findall(r'href="#([^"]+)"', text):
            if href not in ids:
                problems.append(f"{filename}: href #{href} has no anchor")
        if lang == "en":
            visible = re.sub(r"```text.*?```", "", text, flags=re.S)
            for token in ("简体中文", "点击查看", "精选"):
                visible = visible.replace(token, "")
            cjk = [ln.strip() for ln in visible.splitlines() if re.search(r"[\u4e00-\u9fff]", ln)]
            if cjk:
                problems.append("CJK outside English prompts: " + " || ".join(cjk[:6]))
            if re.search(r"[：、。「」]", visible):
                problems.append("full-width punctuation outside English prompts")
    saved = json.loads((ROOT / "gallery.json").read_text(encoding="utf-8"))
    if [e["id"] for e in saved] != [e["id"] for e in entries]:
        problems.append("gallery.json entries do not match the generated index")
    for e in saved:
        if not isinstance(e.get("featured"), bool):
            problems.append(f"gallery.json {e['id']} is missing featured")
        if e.get("added") and not re.fullmatch(r"\d{4}-\d{2}-\d{2}", e["added"]):
            problems.append(f"gallery.json {e['id']} has a bad added date")
        if e.get("featured") and not e.get("added"):
            problems.append(f"gallery.json {e['id']} is featured without an added date")
    return problems


if __name__ == "__main__":
    build()
