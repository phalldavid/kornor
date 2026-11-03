# KORNOR website

The website for **KORNOR Architecture and Structural**, Phnom Penh.

The content is not stored in this repository. It comes from Google:

| What | Where |
|---|---|
| Project details (name, location, year, description…) | Google Sheet **KORNOR Projects Database**, tab **Projects** |
| Project photos | Google Drive › **KORNOR Projects › Projects › `<Project ID>` › Website** |
| Hero, studio, team and expertise photos | Google Drive › **KORNOR Projects › Site Images** |
| Studio text, services, contact details, map | `content/site.json` in this repository |

GitHub Actions reads the Sheet and the Drive folder, compresses every photo to WebP (800 / 1600 / 2400 px wide), builds the pages and publishes them on GitHub Pages.

The full guide for the team (how to add a project, which photos go where) is the **README** in the Google Drive folder.

---

## How updates reach the website

The site rebuilds itself:

- **every 6 hours**, automatically;
- **on demand**: GitHub › **Actions** › **Build and deploy website** › **Run workflow**;
- whenever anything is pushed to `main`.

A rebuild takes about 1–3 minutes. Photos that were already compressed are reused, so only new photos take time.

### Rules the build follows

- A project appears only if it has a **Project ID**, a **Project name** and **Show on website = Yes**.
- Only photos in the project's **Website** subfolder are published. The **Archive** subfolder is never read.
- **Cover photo** (file name) is shown first and used on the Projects grid and the Home page. If empty, the first photo by file name is the cover.
- **Photo order** (optional, comma-separated file names) sets the gallery order. Photos not listed follow in file-name order.
- **Selected work (Home) = Yes** puts the project on the Home page, sorted by **Home order**. It uses the same photos — nothing is uploaded twice.
- Site photos are matched by file name (any extension): `hero`, `studio-hero`, `try-mengheang`, `la-rachun`, `meas-pharavit`, `khem-phalldavid`, `ken-sreynith`, `architecture`, `structural-design`, `masterplanning`, `urban-planning`, `interior-design`, `3d-visualization`.
- Missing photos show a grey placeholder instead of breaking the page.
- JPG, PNG, WebP, HEIC (iPhone) and TIFF are accepted.

---

## One-time setup (≈15 minutes)

Until this is done, the site builds with grey placeholder projects.

### 1. Create a Google service account (a "robot" Google account that can read the files)

1. Open <https://console.cloud.google.com/> and create a project, e.g. `kornor-website`.
2. **APIs & Services › Library**: enable **Google Drive API** and **Google Sheets API**.
3. **APIs & Services › Credentials › Create credentials › Service account**. Name it `kornor-website`. No roles are needed.
4. Open the service account › **Keys › Add key › Create new key › JSON**. A `.json` file downloads. Keep it private — never commit it.
5. Copy the service account's email (looks like `kornor-website@kornor-website.iam.gserviceaccount.com`).

### 2. Share the content with it (read-only)

In Google Drive, **Share** with that email as **Viewer**:

- the **KORNOR Projects** folder;
- the **KORNOR Projects Database** Google Sheet (if it is not inside that folder).

### 3. Give the key to GitHub

Repository › **Settings › Secrets and variables › Actions › New repository secret**

- Name: `GOOGLE_SERVICE_ACCOUNT_JSON`
- Value: paste the entire contents of the `.json` file.

### 4. Turn on GitHub Pages

Repository › **Settings › Pages › Build and deployment › Source: GitHub Actions**.

Then **Actions › Build and deploy website › Run workflow**. The site appears at
**<https://phalldavid.github.io/kornor/>**.

### 5. When ready to go public

The site is hidden from Google while testing (`noindex` and `robots.txt`).
To allow search engines: **Settings › Secrets and variables › Actions › Variables › New variable** `SITE_INDEXABLE` = `true`, then run the workflow.

For a custom domain (e.g. `kornor.com.kh`): **Settings › Pages › Custom domain**, then add the DNS records GitHub shows at your domain registrar.

---

## Editing the fixed text

Studio story, vision, mission, people, services, process, phone, Telegram, address and map pin are in [`content/site.json`](content/site.json). Edit it on GitHub (pencil icon) and commit — the site rebuilds.

Empty values are hidden automatically: `email`, `office_hours`, `facebook`, `instagram`, `portfolio_pdf`.
Setting `formspree_id` (free account at formspree.io) shows a contact form; otherwise the Contact page shows Telegram and Call buttons.

## Running it on a computer (optional)

```bash
pip install -r requirements.txt
python scripts/build.py --source sample          # placeholder content
python scripts/build.py --source local --content-dir path/to/test-folder
GOOGLE_SERVICE_ACCOUNT_JSON="$(cat key.json)" python scripts/build.py --source google
python -m http.server -d dist 8000               # open http://localhost:8000
```

A local test folder uses the same layout as Drive: `projects.csv` (exported Projects tab), `Projects/<ID>/Website/…`, `Site Images/<Home|Studio|Team|Expertise>/…`.

## Files

```
scripts/build.py            reads Sheet + Drive, compresses photos, renders pages
templates/                  page layouts (Jinja2)
static/css/site.css         styles
static/js/site.js           mobile menu, header, filter, lightbox
static/img/                 logo, mark, favicon
content/site.json           fixed text and contact details
content/sample-projects.csv placeholders used before Google is connected
.github/workflows/deploy.yml build and publish on GitHub Pages
```
