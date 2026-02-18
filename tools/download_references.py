#!/usr/bin/env python3
"""
Download champion, item, and augment reference icons from Community Dragon.
These are used by the vision engine for template matching.
"""
import json
import tempfile
import urllib.request
import sys
from pathlib import Path

CDN_BASE = "https://raw.communitydragon.org/latest/game/"
CDRAGON_CACHE = Path(tempfile.gettempdir()) / "cdragon_tft.json"
REFERENCES_DIR = Path(__file__).parent.parent / "references"


def tex_to_url(tex_path: str) -> str:
    """Convert a .tex asset path to a CDN PNG URL."""
    return CDN_BASE + tex_path.lower().replace(".tex", ".png")


def download(url: str, dest: Path) -> bool:
    """Download a URL to a file. Returns True on success."""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req) as resp:
            dest.write_bytes(resp.read())
        return True
    except Exception as e:
        print(f"  FAILED: {url} — {e}")
        return False


def main():
    with open(CDRAGON_CACHE, encoding="utf-8") as f:
        data = json.load(f)

    set_data = data["sets"]["16"]
    items = data["items"]

    # Download champion square icons (tileIcon = HUD square, best for matching)
    champ_dir = REFERENCES_DIR / "champions"
    champ_dir.mkdir(parents=True, exist_ok=True)
    champs = [c for c in set_data["champions"]
              if c["apiName"].startswith("TFT16_")
              and c.get("cost", 0) >= 1
              and not any(x in c["apiName"] for x in ["PVE", "Carousel", "Prop", "Minion", "XerathZap"])]

    print(f"Downloading {len(champs)} champion icons...")
    ok = 0
    for c in champs:
        icon = c.get("tileIcon") or c.get("squareIcon") or c.get("icon", "")
        if not icon:
            print(f"  SKIP {c['apiName']}: no icon path")
            continue
        dest = champ_dir / f"{c['apiName']}.png"
        if dest.exists():
            ok += 1
            continue
        url = tex_to_url(icon)
        if download(url, dest):
            ok += 1
            print(f"  {c['name']}")
    print(f"  {ok}/{len(champs)} champion icons downloaded\n")

    # Download item component icons
    item_dir = REFERENCES_DIR / "items"
    item_dir.mkdir(parents=True, exist_ok=True)
    # Get unique components (TFT_Item_ prefix, tagged as component)
    components = [i for i in items
                  if i.get("apiName", "").startswith("TFT_Item_")
                  and "component" in str(i.get("tags", [])).lower()
                  and i.get("name")]
    # Deduplicate by name
    seen = set()
    unique_components = []
    for i in components:
        if i["name"] not in seen:
            seen.add(i["name"])
            unique_components.append(i)

    print(f"Downloading {len(unique_components)} item component icons...")
    ok = 0
    for i in unique_components:
        icon = i.get("icon", "")
        if not icon:
            continue
        dest = item_dir / f"{i['apiName']}.png"
        if dest.exists():
            ok += 1
            continue
        url = tex_to_url(icon)
        if download(url, dest):
            ok += 1
            print(f"  {i['name']}")
    print(f"  {ok}/{len(unique_components)} component icons downloaded\n")

    # Download completed item icons (non-component, non-augment, with recipes)
    completed = [i for i in items
                 if i.get("apiName", "").startswith("TFT_Item_")
                 and "component" not in str(i.get("tags", [])).lower()
                 and i.get("composition")
                 and i.get("name")
                 and i.get("icon")]
    print(f"Downloading {len(completed)} completed item icons...")
    ok = 0
    for i in completed:
        dest = item_dir / f"{i['apiName']}.png"
        if dest.exists():
            ok += 1
            continue
        url = tex_to_url(i["icon"])
        if download(url, dest):
            ok += 1
    print(f"  {ok}/{len(completed)} completed item icons downloaded\n")

    # Download augment icons (Tocker's augments only)
    aug_dir = REFERENCES_DIR / "augments"
    aug_dir.mkdir(parents=True, exist_ok=True)
    augments = [i for i in items
                if (i["apiName"].startswith("TFT16_Augment") or
                    i["apiName"].startswith("TFT16_Teamup"))
                and i.get("icon")
                and "Missing" not in i.get("icon", "")]

    print(f"Downloading {len(augments)} augment icons...")
    ok = 0
    skip = 0
    for a in augments:
        dest = aug_dir / f"{a['apiName']}.png"
        if dest.exists():
            ok += 1
            continue
        url = tex_to_url(a["icon"])
        if download(url, dest):
            ok += 1
            print(f"  {a.get('name', a['apiName'])}")
        else:
            skip += 1
    print(f"  {ok}/{len(augments)} augment icons downloaded ({skip} failed)\n")

    print("Done! Reference images saved to:", REFERENCES_DIR)


if __name__ == "__main__":
    main()
