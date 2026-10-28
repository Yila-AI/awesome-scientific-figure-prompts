#!/usr/bin/env python3
"""Generate figures with Evolink and record every attempt.

Usage:
  python3 -I tools/gen.py <figure-id>[:en|:zh] ...   # one attempt each; default en
  python3 -I tools/gen.py --all                       # every figure, en and zh

Each figure is a JSON file in prompts/<theme>/<id>.json:
  {"id", "theme", "title": {"zh","en"}, "technique", "technique_en",
   "style": "A"|"B"|"W"|"D"|"S", "size": "16:9", "content": {"zh","en"},
   optional "author", "author_url", "featured", "added"}

You can also generate the image by hand in any Gemini or ChatGPT UI and
commit gallery/<theme>/<id>-<lang>.jpg. See CONTRIBUTING.md. tools/gen.py
is optional and needs an Evolink key.

The prompt sent is content.<lang> (with the 【】 slot brackets removed) plus
styles.json[style][lang]. Images land in images/<theme>/<id>-<lang>-<n>.png;
every attempt is appended to
records.jsonl. The key is read from $EVOLINK_API_KEY or ~/.config/evolink/key.
"""
import json
import os
import pathlib
import sys
import time
import urllib.error
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parent.parent
BASE = "https://api.evolink.ai"
MODEL = os.environ.get("EVOLINK_MODEL", "gemini-3.1-flash-lite-image")
POLL_SECONDS = 4
USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) scientific-figure-prompts/1.0"
TIMEOUT_SECONDS = 300


def api_key():
    key = os.environ.get("EVOLINK_API_KEY", "").strip()
    for path in (ROOT / "evolink-key.txt", pathlib.Path.home() / ".config/evolink/key"):
        if not key and path.exists():
            key = path.read_text().strip()
    if not key:
        sys.exit("No Evolink key: paste it into evolink-key.txt or set EVOLINK_API_KEY")
    return key


def request(method, url, key, body=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Authorization", f"Bearer {key}")
    req.add_header("Content-Type", "application/json")
    req.add_header("User-Agent", USER_AGENT)
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as err:
        raise RuntimeError(f"HTTP {err.code}: {err.read().decode(errors='replace')[:500]}")


def find_urls(value):
    """Collect every http(s) URL in a task response, whatever its shape."""
    if isinstance(value, str):
        return [value] if value.startswith("http") else []
    if isinstance(value, dict):
        return [u for v in value.values() for u in find_urls(v)]
    if isinstance(value, list):
        return [u for v in value for u in find_urls(v)]
    return []


def load_figures():
    figures = {}
    for path in sorted((ROOT / "prompts").glob("*/*.json")):
        fig = json.loads(path.read_text())
        figures[fig["id"]] = fig
    return figures


def build_prompt(fig, styles, lang):
    content = fig["content"][lang].replace("【", "").replace("】", "").strip()
    return f"{content}\n\n{styles[fig['style']][lang].strip()}"


def next_attempt(fig, lang):
    folder = ROOT / "images" / fig["theme"]
    folder.mkdir(parents=True, exist_ok=True)
    n = 1
    while (folder / f"{fig['id']}-{lang}-{n}.png").exists():
        n += 1
    return folder / f"{fig['id']}-{lang}-{n}.png", n


def generate(fig, styles, key, lang):
    prompt = build_prompt(fig, styles, lang)
    out, attempt = next_attempt(fig, lang)
    started = time.time()
    created = request("POST", f"{BASE}/v1/images/generations", key, {
        "model": MODEL,
        "prompt": prompt,
        "size": fig.get("size", "16:9"),
        "quality": "1K",
    })
    task_id = created.get("id") or created.get("task_id") or (created.get("data") or {}).get("id")
    if not task_id:
        raise RuntimeError(f"No task id in response: {json.dumps(created)[:500]}")

    while True:
        task = request("GET", f"{BASE}/v1/tasks/{task_id}", key)
        status = str(task.get("status") or (task.get("data") or {}).get("status") or "").lower()
        if status in {"completed", "succeeded", "success"}:
            break
        if status in {"failed", "cancelled", "canceled", "error"}:
            raise RuntimeError(f"Task {task_id} {status}: {json.dumps(task)[:500]}")
        if time.time() - started > TIMEOUT_SECONDS:
            raise RuntimeError(f"Task {task_id} timed out, last status {status!r}")
        time.sleep(POLL_SECONDS)

    urls = [u for u in find_urls(task) if "/v1/tasks/" not in u]
    if not urls:
        raise RuntimeError(f"Task {task_id} finished without an image URL: {json.dumps(task)[:500]}")
    image = urllib.request.Request(urls[0], headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(image, timeout=120) as resp:
            out.write_bytes(resp.read())
    except urllib.error.HTTPError as err:
        raise RuntimeError(f"Task {task_id} image download HTTP {err.code}; urls={urls}")

    record = {
        "id": fig["id"],
        "theme": fig["theme"],
        "lang": lang,
        "attempt": attempt,
        "image": str(out.relative_to(ROOT)),
        "model": MODEL,
        "size": fig.get("size", "16:9"),
        "style": fig["style"],
        "prompt": prompt,
        "task_id": task_id,
        "seconds": round(time.time() - started, 1),
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "usable": None,
        "notes": "",
    }
    with open(ROOT / "records.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")
    return record


def main():
    args = sys.argv[1:]
    if not args:
        sys.exit(__doc__)
    figures = load_figures()
    styles = json.loads((ROOT / "styles.json").read_text())
    jobs = [f"{i}:{l}" for i in figures for l in ("en", "zh")] if args == ["--all"] else args
    key = api_key()
    for job in jobs:
        fig_id, _, lang = job.partition(":")
        lang = lang or "en"
        if fig_id not in figures:
            print(f"skip {fig_id}: no prompts/*/{fig_id}.json")
            continue
        try:
            rec = generate(figures[fig_id], styles, key, lang)
            print(f"ok   {job} #{rec['attempt']} -> {rec['image']} ({rec['seconds']}s)")
        except Exception as err:  # keep going with the next figure
            print(f"fail {job}: {err}")


if __name__ == "__main__":
    main()
