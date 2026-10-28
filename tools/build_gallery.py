#!/usr/bin/env python3
"""Build the publishable gallery from prompts/ and records.jsonl.

For every template and language, the first image marked usable is published;
gallery_extra lists further usable attempts to publish as alternates. Writes:
  gallery/<theme>/<id>-<lang>[-<attempt>].jpg   compressed images
  gallery/cover.jpg                              3x3 cover of the featured set
  gallery.json                                   machine-readable index
  README.md / README_en.md                       generated, do not edit by hand
"""
import json
import pathlib
import time

from PIL import Image

ROOT = pathlib.Path(__file__).resolve().parent.parent
MODEL_NAME = "Nano Banana 2 Lite (gemini-3.1-flash-lite-image, 1K)"
YILA_URL = "https://yila.ai/?utm_source=github&utm_medium=referral&utm_campaign=sci-figure-prompts"
REPO_TITLE = "Awesome Scientific Figure Prompts"

THEMES = [
    ("graphical-abstract", "图形摘要", "Graphical Abstract"),
    ("signaling-pathway", "信号通路", "Signaling Pathway"),
    ("medical-illustration", "医学插图", "Medical Illustration"),
    ("experimental-workflow", "实验流程", "Experimental Workflow"),
    ("materials-energy", "材料与能源", "Materials & Energy"),
    ("earth-environment", "环境与地球", "Earth & Environment"),
    ("ai-computing", "AI 与计算机", "AI & Computing"),
    ("engineering-systems", "工程系统", "Engineering Systems"),
    ("chemistry-instruments", "化学与仪器", "Chemistry & Instruments"),
    ("plant-agriculture", "农学与植物", "Plant & Agriculture"),
    ("social-science", "人文社科", "Social Science"),
]
STYLE_NAMES = {"A": ("期刊式扁平矢量", "flat vector schematic"),
               "B": ("柔和半写实插图", "soft semi-realistic illustration"),
               "W": ("扁平流程图", "flat workflow"),
               "D": ("期刊式示意框图", "schematic diagram"),
               "S": ("期刊式科学插画", "scientific illustration")}
FEATURED = [("wound-healing-stages", "en"), ("liver-fibrosis", "en"), ("nanoparticle-tumor-delivery", "en"),
            ("cgas-sting", "zh"), ("mouse-model-dosing", "zh"), ("alzheimers-brain", "zh"),
            ("fracture-healing", "zh"), ("hydrogel-wound", "en"), ("tgfb-smad", "zh")]
EXTRA = [("exercise-glut4", "zh", 2), ("scrna-seq-workflow", "zh", 5)]


def load():
    figs = {}
    for p in sorted((ROOT / "prompts").glob("*/*.json")):
        f = json.loads(p.read_text())
        figs[f["id"]] = f
    recs = [json.loads(l) for l in (ROOT / "records.jsonl").read_text().splitlines() if l]
    return figs, recs, json.loads((ROOT / "styles.json").read_text())


def publish(rec, suffix=""):
    out = ROOT / "gallery" / rec["theme"] / f"{rec['id']}-{rec['lang']}{suffix}.jpg"
    out.parent.mkdir(parents=True, exist_ok=True)
    Image.open(ROOT / rec["image"]).convert("RGB").save(out, "JPEG", quality=86, optimize=True)
    return str(out.relative_to(ROOT))


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
                    images.append({"lang": lang, "src": publish(ok[0]), "attempt": ok[0]["attempt"]})
            for eid, lang, attempt in EXTRA:
                if eid == fid:
                    rec = next(r for r in mine if r["lang"] == lang and r["attempt"] == attempt)
                    images.append({"lang": lang, "src": publish(rec, f"-{attempt}"), "attempt": attempt})
            entries.append({
                "id": fid, "theme": theme, "title": fig["title"], "technique": fig.get("technique", ""),
                "style": fig["style"], "size": fig["size"], "images": images,
                "generations": len(mine),
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
    total = sum(len(e["images"]) for e in entries)
    print(f"{len(entries)} templates, {total} images")


def make_cover(entries):
    by = {(e["id"], i["lang"]): i["src"] for e in entries for i in e["images"]}
    tile_w, tile_h, gap = 640, 400, 12
    cover = Image.new("RGB", (tile_w * 3 + gap * 4, tile_h * 3 + gap * 4), "white")
    for k, key in enumerate(FEATURED):
        im = Image.open(ROOT / by[key]).convert("RGB")
        im.thumbnail((tile_w, tile_h))
        x = gap + (k % 3) * (tile_w + gap) + (tile_w - im.width) // 2
        y = gap + (k // 3) * (tile_h + gap) + (tile_h - im.height) // 2
        cover.paste(im, (x, y))
    cover.save(ROOT / "gallery" / "cover.jpg", "JPEG", quality=86, optimize=True)


def render(entries, lang):
    zh = lang == "zh"
    today = time.strftime("%Y-%m-%d")
    total = sum(len(e["images"]) for e in entries)
    L = []
    L += [f"# {REPO_TITLE}", ""]
    L += ["[![License: CC BY 4.0](https://img.shields.io/badge/License-CC%20BY%204.0-lightgrey.svg)](https://creativecommons.org/licenses/by/4.0/)",
          "![PRs welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg)", ""]
    L += ["[中文](README.md) | [English](README_en.md)", ""]
    if zh:
        L += ["**可以直接改成自己课题的科研绘图提示词模板，覆盖生物医学、材料能源、环境、AI、工程、化学、农学和社科。** 每条提示词都配有真实出图，"
              "【】里的内容换成你的研究对象，其余部分照抄即可。", ""]
    else:
        L += ["**Scientific figure prompt templates you can adapt to your own research, across biomedicine, materials and energy, environment, AI, engineering, chemistry, plant science and social science.** Every prompt comes with "
              "real outputs. Replace the text inside 【】 with your own topic and keep the rest.", ""]
    L += ["![cover](gallery/cover.jpg)", ""]
    L += ["## " + ("统计" if zh else "Statistics"), "",
          f"| {'模板' if zh else 'Templates'} | {'示例图' if zh else 'Images'} | {'模型' if zh else 'Model'} | {'更新' if zh else 'Updated'} |",
          "|---|---|---|---|", f"| {len(entries)} | {total} | {MODEL_NAME} | {today} |", ""]
    L += ["## " + ("怎么用" if zh else "How to use"), ""]
    if zh:
        L += ["1. 找到和你的图类型最接近的模板，复制提示词。",
              "2. 把【】里的内容换成你的研究主题、结构和步骤，然后删掉【】。保留风格段落不动。",
              "3. 粘贴到支持图像生成的模型里（例如 Gemini、ChatGPT）。图里的文字保持英文短标签，出错率最低。",
              f"4. 不想自己拆模块，也可以把论文摘要交给 [YILA]({YILA_URL})，让它按这些模板帮你写提示词并出图。",
              "5. 出图后请自己核对箭头方向、结构位置和标签拼写。这些是示意图初稿，用于论文前请按你的课题修改。", ""]
    else:
        L += ["1. Pick the template closest to the figure you need and copy its prompt.",
              "2. Replace the text inside 【】 with your own topic, structures and steps, then delete the 【】 marks. Keep the style paragraph unchanged.",
              "3. Paste it into an image model such as Gemini or ChatGPT. Short English labels give the fewest text errors.",
              f"4. Or hand your abstract to [YILA]({YILA_URL}) and let it fill the template and draw the figure.",
              "5. Always check arrows, structure positions and label spelling. These are first drafts, not submission-ready figures.", ""]
    L += ["## " + ("目录" if zh else "Contents"), ""]
    for theme, tzh, ten in THEMES:
        items = [e for e in entries if e["theme"] == theme]
        L.append(f"- **{tzh if zh else ten}**：" + "、".join(
            f"[No. {e['no']} {e['title'][lang]}](#no-{e['no']})" for e in items))
    L.append("")
    for theme, tzh, ten in THEMES:
        L += [f"## {tzh if zh else ten}", ""]
        for e in [e for e in entries if e["theme"] == theme]:
            L += [f'<a id="no-{e["no"]}"></a>', "", f"### No. {e['no']}：{e['title'][lang]}", ""]
            sz, se = STYLE_NAMES[e["style"]]
            L += [(f"写法技巧：**{e['technique']}**　·　风格：{sz}　·　比例：{e['size']}" if zh else
                   f"Technique: **{e['technique']}** · Style: {se} · Aspect ratio: {e['size']}"), ""]
            heads = [("英文提示词出图" if i["lang"] == "en" else "中文提示词出图") if zh else
                     ("English prompt" if i["lang"] == "en" else "Chinese prompt") for i in e["images"]]
            L += ["| " + " | ".join(heads) + " |", "|" + "---|" * len(heads),
                  "| " + " | ".join(f'<img src="{i["src"]}" width="420">' for i in e["images"]) + " |", ""]
            first, second = (("zh", "en") if zh else ("en", "zh"))
            label = {"zh": "中文提示词" if zh else "Chinese prompt", "en": "English prompt"}
            L += [f"**{label[first]}**", "", "```text", e["prompt"][first], "```", ""]
            L += [f"<details><summary>{label[second]}</summary>", "", "```text", e["prompt"][second], "```", "", "</details>", ""]
            L += [(f"模型：{MODEL_NAME}　·　这条提示词共生成 {e['generations']} 次，展示的是核对通过的结果" if zh else
                   f"Model: {MODEL_NAME} · Generated {e['generations']} times in total; shown are the outputs that passed review"), ""]
            L += ["---", ""]
    L += ["## " + ("投稿" if zh else "Contributing"), ""]
    L += [("欢迎通过 Pull Request 或 Issue 提交你的提示词和出图，收录后会署名。发现科学错误也请提 Issue。" if zh else
           "Submit your prompts and outputs through a pull request or an issue; accepted entries are credited. Please open an issue for any scientific error."), ""]
    L += ["## " + ("许可" if zh else "License"), ""]
    L += [("提示词以 [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/) 发布。示例图由 AI 生成，带有模型自带的 SynthID 水印。" if zh else
           "Prompts are released under [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/). Example images are AI-generated and carry the model's SynthID watermark."), ""]
    return "\n".join(L)


if __name__ == "__main__":
    build()
