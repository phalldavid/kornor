#!/usr/bin/env python3
"""Build the KORNOR website.

Reads project data from the Google Sheet "KORNOR Projects Database" and photos
from the "KORNOR Projects" Google Drive folder, converts every photo to WebP in
three sizes, and writes a static site to ./dist.

Sources (chosen with --source, default "auto"):
  google  Google Sheet + Drive, using a service account whose JSON key is in the
          environment variable GOOGLE_SERVICE_ACCOUNT_JSON.
  local   A folder on disk with the same layout as the Drive folder, plus a
          projects.csv exported from the sheet (for testing): --content-dir PATH
  sample  Placeholder projects from content/sample-projects.csv, no photos.
  auto    google if GOOGLE_SERVICE_ACCOUNT_JSON is set, otherwise sample.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import os
import re
import shutil
import sys
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from jinja2 import Environment, FileSystemLoader, select_autoescape
from PIL import Image, ImageOps

try:  # HEIC/HEIF photos from iPhones
    from pillow_heif import register_heif_opener
    register_heif_opener()
except Exception:  # pragma: no cover - optional dependency
    pass

ROOT = Path(__file__).resolve().parent.parent
IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".heic", ".heif", ".tif", ".tiff"}
WIDTHS = (800, 1600, 2400)
WEBP_QUALITY = 80

COL = {
    "id": "Project ID",
    "show": "Show on website",
    "selected": "Selected work (Home)",
    "home_order": "Home order",
    "name": "Project name",
    "slug": "Web address (auto)",
    "category": "Category",
    "type": "Project type",
    "location": "Location",
    "year": "Year",
    "size": "Size",
    "size_unit": "Size unit",
    "role": "Our role",
    "status": "Status",
    "description": "Short description",
    "cover": "Cover photo (file name)",
    "photo_order": "Photo order (optional)",
}


# --------------------------------------------------------------------------- sources
@dataclass
class ImageRef:
    name: str
    key: str            # stable id + modified time, used for caching
    fetch: Callable[[], bytes]


class SampleSource:
    label = "sample placeholders"

    def project_rows(self) -> list[dict]:
        with open(ROOT / "content" / "sample-projects.csv", newline="", encoding="utf-8") as f:
            return list(csv.DictReader(f))

    def project_images(self, project_id: str) -> list[ImageRef]:
        return []

    def site_image(self, subfolder: str, filename_stem: str) -> ImageRef | None:
        return None


class LocalSource:
    """Same layout as the Drive folder, on disk (used for testing)."""
    label = "local folder"

    def __init__(self, root: Path, cfg: dict):
        self.root = root
        self.g = cfg["google"]

    def project_rows(self) -> list[dict]:
        with open(self.root / "projects.csv", newline="", encoding="utf-8") as f:
            return list(csv.DictReader(f))

    def _ref(self, p: Path) -> ImageRef:
        st = p.stat()
        return ImageRef(p.name, f"{p.resolve()}:{st.st_mtime_ns}:{st.st_size}", p.read_bytes)

    def project_images(self, project_id: str) -> list[ImageRef]:
        d = self.root / self.g["projects_folder_name"] / project_id / self.g["website_subfolder_name"]
        if not d.is_dir():
            return []
        return [self._ref(p) for p in sorted(d.iterdir()) if p.suffix.lower() in IMAGE_EXTS]

    def site_image(self, subfolder: str, filename_stem: str) -> ImageRef | None:
        d = self.root / self.g["site_images_folder_name"] / subfolder
        if not d.is_dir():
            return None
        for p in sorted(d.iterdir()):
            if p.stem.lower() == filename_stem.lower() and p.suffix.lower() in IMAGE_EXTS:
                return self._ref(p)
        return None


class GoogleSource:
    label = "Google Sheet + Drive"
    DRIVE = "https://www.googleapis.com/drive/v3/files"
    SHEETS = "https://sheets.googleapis.com/v4/spreadsheets"

    def __init__(self, cfg: dict):
        from google.oauth2 import service_account
        from google.auth.transport.requests import AuthorizedSession

        info = json.loads(os.environ["GOOGLE_SERVICE_ACCOUNT_JSON"])
        creds = service_account.Credentials.from_service_account_info(
            info,
            scopes=[
                "https://www.googleapis.com/auth/drive.readonly",
                "https://www.googleapis.com/auth/spreadsheets.readonly",
            ],
        )
        self.http = AuthorizedSession(creds)
        self.g = cfg["google"]
        self._children: dict[str, list[dict]] = {}

    def _get(self, url: str, **params) -> dict:
        r = self.http.get(url, params=params, timeout=60)
        if r.status_code != 200:
            raise SystemExit(f"Google API error {r.status_code} for {url}: {r.text[:400]}")
        return r.json()

    def children(self, folder_id: str) -> list[dict]:
        if folder_id in self._children:
            return self._children[folder_id]
        files, token = [], None
        while True:
            params = dict(
                q=f"'{folder_id}' in parents and trashed = false",
                fields="nextPageToken, files(id, name, mimeType, modifiedTime)",
                pageSize=1000,
                supportsAllDrives="true",
                includeItemsFromAllDrives="true",
            )
            if token:
                params["pageToken"] = token
            data = self._get(self.DRIVE, **params)
            files += data.get("files", [])
            token = data.get("nextPageToken")
            if not token:
                break
        self._children[folder_id] = files
        return files

    def child_folder(self, parent_id: str, name: str) -> str | None:
        for f in self.children(parent_id):
            if f["mimeType"] == "application/vnd.google-apps.folder" and f["name"].strip().lower() == name.strip().lower():
                return f["id"]
        return None

    def _ref(self, f: dict) -> ImageRef:
        def fetch(fid=f["id"]):
            r = self.http.get(f"{self.DRIVE}/{fid}", params={"alt": "media", "supportsAllDrives": "true"}, timeout=300)
            r.raise_for_status()
            return r.content
        return ImageRef(f["name"], f"{f['id']}:{f['modifiedTime']}", fetch)

    def _images_in(self, folder_id: str) -> list[ImageRef]:
        files = [f for f in self.children(folder_id)
                 if f["mimeType"].startswith("image/") or Path(f["name"]).suffix.lower() in IMAGE_EXTS]
        return [self._ref(f) for f in sorted(files, key=lambda f: f["name"].lower())]

    def project_rows(self) -> list[dict]:
        data = self._get(f"{self.SHEETS}/{self.g['sheet_id']}/values/Projects!A1:Z")
        values = data.get("values", [])
        if not values:
            return []
        header = [h.strip() for h in values[0]]
        return [dict(zip(header, row + [""] * (len(header) - len(row)))) for row in values[1:]]

    def project_images(self, project_id: str) -> list[ImageRef]:
        projects = self.child_folder(self.g["root_folder_id"], self.g["projects_folder_name"])
        if not projects:
            raise SystemExit("Could not find the 'Projects' folder. Is the KORNOR Projects folder shared with the service account?")
        pf = self.child_folder(projects, project_id)
        if not pf:
            return []
        web = self.child_folder(pf, self.g["website_subfolder_name"])
        return self._images_in(web) if web else []

    def site_image(self, subfolder: str, filename_stem: str) -> ImageRef | None:
        si = self.child_folder(self.g["root_folder_id"], self.g["site_images_folder_name"])
        sub = si and self.child_folder(si, subfolder)
        if not sub:
            return None
        for ref in self._images_in(sub):
            if Path(ref.name).stem.lower() == filename_stem.lower():
                return ref
        return None


# --------------------------------------------------------------------------- images
class ImageProcessor:
    def __init__(self, out: Path, cache: Path, base: str):
        self.out, self.cache, self.base = out, cache, base
        self.cache.mkdir(parents=True, exist_ok=True)
        self.count = 0

    def process(self, ref: ImageRef, rel_dir: str, alt: str = "") -> dict | None:
        digest = hashlib.sha1(ref.key.encode()).hexdigest()[:16]
        meta_path = self.cache / f"{digest}.json"
        stem = slugify(Path(ref.name).stem) or "image"
        if meta_path.exists():
            meta = json.loads(meta_path.read_text())
        else:
            try:
                img = Image.open(io.BytesIO(ref.fetch()))
                img = ImageOps.exif_transpose(img)
            except Exception as e:  # unreadable file: skip, don't fail the whole site
                print(f"  ! skipped {ref.name}: {e}", file=sys.stderr)
                return None
            has_alpha = img.mode in ("RGBA", "LA") or (img.mode == "P" and "transparency" in img.info)
            img = img.convert("RGBA" if has_alpha else "RGB")
            w, h = img.size
            sizes = sorted({min(w, tw) for tw in WIDTHS})
            for tw in sizes:
                th = round(h * tw / w)
                im = img if tw == w else img.resize((tw, th), Image.LANCZOS)
                im.save(self.cache / f"{digest}-{tw}.webp", "WEBP", quality=WEBP_QUALITY, method=6)
            meta = {"w": w, "h": h, "sizes": sizes}
            meta_path.write_text(json.dumps(meta))
        dest = self.out / "media" / rel_dir
        dest.mkdir(parents=True, exist_ok=True)
        srcset = []
        for tw in meta["sizes"]:
            name = f"{stem}-{tw}.webp"
            shutil.copyfile(self.cache / f"{digest}-{tw}.webp", dest / name)
            srcset.append((tw, f"{self.base}/media/{rel_dir}/{name}"))
        self.count += 1
        default = next((u for w, u in srcset if w >= 1600), srcset[-1][1])
        return {
            "src": default,
            "srcset": ", ".join(f"{u} {w}w" for w, u in srcset),
            "width": meta["w"],
            "height": meta["h"],
            "ratio": meta["w"] / meta["h"],
            "alt": alt,
            "name": ref.name,
        }


# --------------------------------------------------------------------------- helpers
def slugify(text: str) -> str:
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def yes(v: str) -> bool:
    return str(v).strip().lower() in {"yes", "y", "true", "1"}


def to_int(v, default=None):
    try:
        return int(float(str(v).replace(",", "").strip()))
    except (ValueError, TypeError):
        return default


def fmt_size(size: str, unit: str) -> str:
    n = to_int(size)
    if n is None:
        return str(size).strip()
    return f"{n:,} {unit}".strip()


def ordered_images(refs: list[ImageRef], order: str, cover: str) -> list[ImageRef]:
    by_name = {r.name.lower(): r for r in refs}
    seq = []
    if order.strip():
        for n in [x.strip().lower() for x in order.split(",") if x.strip()]:
            if n in by_name and by_name[n] not in seq:
                seq.append(by_name[n])
        seq += [r for r in refs if r not in seq]  # anything not listed still shows, after the listed ones
    else:
        seq = list(refs)
    if cover.strip() and cover.strip().lower() in by_name:
        c = by_name[cover.strip().lower()]
        seq = [c] + [r for r in seq if r is not c]
    return seq


# --------------------------------------------------------------------------- build
def build(args) -> None:
    cfg = json.loads((ROOT / "content" / "site.json").read_text(encoding="utf-8"))
    base = args.base.rstrip("/")
    out = Path(args.out).resolve()
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)

    src_name = args.source
    if src_name == "auto":
        src_name = "google" if os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON") else "sample"
    if src_name == "google":
        source = GoogleSource(cfg)
    elif src_name == "local":
        if not args.content_dir:
            raise SystemExit("--source local needs --content-dir")
        source = LocalSource(Path(args.content_dir), cfg)
    else:
        source = SampleSource()
    print(f"Content source: {source.label}")

    proc = ImageProcessor(out, Path(args.cache).resolve(), base)

    # ---- projects
    projects, seen = [], set()
    for row in source.project_rows():
        pid = (row.get(COL["id"]) or "").strip()
        name = (row.get(COL["name"]) or "").strip()
        if not pid or not name or not yes(row.get(COL["show"], "")):
            continue
        slug = (row.get(COL["slug"]) or "").strip() or slugify(name) or slugify(pid)
        base_slug, n = slug, 2
        while slug in seen:
            slug, n = f"{base_slug}-{n}", n + 1
        seen.add(slug)
        refs = ordered_images(source.project_images(pid), row.get(COL["photo_order"], "") or "", row.get(COL["cover"], "") or "")
        images = []
        for i, ref in enumerate(refs):
            im = proc.process(ref, f"projects/{slug}", alt=f"{name}, photo {i + 1}")
            if im:
                images.append(im)
        p = {
            "id": pid,
            "slug": slug,
            "name": name,
            "category": (row.get(COL["category"]) or "").strip(),
            "type": (row.get(COL["type"]) or "").strip(),
            "location": (row.get(COL["location"]) or "").strip(),
            "year": (row.get(COL["year"]) or "").strip(),
            "size": fmt_size(row.get(COL["size"], ""), (row.get(COL["size_unit"]) or "").strip()) if (row.get(COL["size"]) or "").strip() else "",
            "role": (row.get(COL["role"]) or "").strip(),
            "status": (row.get(COL["status"]) or "").strip(),
            "description": (row.get(COL["description"]) or "").strip(),
            "selected": yes(row.get(COL["selected"], "")),
            "home_order": to_int(row.get(COL["home_order"]), 999),
            "images": images,
            "cover": images[0] if images else None,
            "url": f"{base}/projects/{slug}/",
        }
        p["meta"] = " · ".join(x for x in (p["type"], p["location"], p["year"]) if x)
        projects.append(p)
        print(f"  project {pid} '{name}': {len(images)} photo(s)")

    for i, p in enumerate(projects):
        p["prev"] = projects[i - 1] if i > 0 else None
        p["next"] = projects[i + 1] if i < len(projects) - 1 else None
    featured = sorted([p for p in projects if p["selected"]], key=lambda p: p["home_order"])
    categories = [c for c in dict.fromkeys(p["category"] for p in projects) if c]

    # ---- site images (file-name stems from the "Site Images" tab)
    def site_img(sub, stem, alt):
        ref = source.site_image(sub, stem)
        return proc.process(ref, f"site/{slugify(sub)}", alt=alt) if ref else None

    images = {
        "hero": site_img("Home", "hero", "KORNOR project"),
        "studio-hero": site_img("Studio", "studio-hero", "The KORNOR studio"),
    }
    for person in cfg["studio"]["founders"] + cfg["studio"]["team"]:
        images[person["image"]] = site_img("Team", person["image"], f"Portrait of {person['name']}")
    for s in cfg["services"]:
        images[s["image"]] = site_img("Expertise", s["image"], s["name"])

    # ---- render
    env = Environment(loader=FileSystemLoader(ROOT / "templates"), autoescape=select_autoescape(["html", "xml"]),
                      trim_blocks=True, lstrip_blocks=True)
    svg = lambda f: (ROOT / "static" / "img" / f).read_text()
    env.globals.update(
        base=base, site=cfg, images=images, projects=projects, featured=featured, categories=categories,
        logo_svg=svg("logo.svg"), mark_svg=svg("mark.svg"), indexable=args.indexable,
    )

    def render(template: str, path: str, **ctx):
        dest = out / path
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(env.get_template(template).render(**ctx), encoding="utf-8")

    render("home.html", "index.html", page="home")
    render("projects.html", "projects/index.html", page="projects", title="Projects")
    for p in projects:
        render("project.html", f"projects/{p['slug']}/index.html", page="projects", title=p["name"], project=p)
    render("expertise.html", "expertise/index.html", page="expertise", title="Expertise")
    render("studio.html", "studio/index.html", page="studio", title="Studio")
    render("contact.html", "contact/index.html", page="contact", title="Contact")
    render("404.html", "404.html", page="404", title="Page not found")

    shutil.copytree(ROOT / "static", out / "static")
    (out / ".nojekyll").write_text("")
    (out / "robots.txt").write_text("User-agent: *\n" + ("Allow: /\n" if args.indexable else "Disallow: /\n"))
    print(f"Built {len(projects)} project(s), {len(featured)} selected, {proc.count} image(s) -> {out}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--source", choices=["auto", "google", "local", "sample"], default="auto")
    ap.add_argument("--content-dir", help="folder for --source local")
    ap.add_argument("--base", default="", help="URL path prefix, e.g. /kornor-website for GitHub Pages")
    ap.add_argument("--out", default=str(ROOT / "dist"))
    ap.add_argument("--cache", default=str(ROOT / ".cache" / "media"))
    ap.add_argument("--indexable", action="store_true",
                    help="allow search engines (default: hidden from Google while the site is in testing)")
    build(ap.parse_args())


if __name__ == "__main__":
    main()
