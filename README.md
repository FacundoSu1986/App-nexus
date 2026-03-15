# App-nexus — Skyrim Mod Compatibility Manager

**App-nexus** is a mod compatibility manager for **Skyrim Special Edition**.

> 💡 *Hobby project created by a Skyrim enthusiast with the help of AIs
> (Claude, GitHub Copilot, Gemini, Kimi). Contributions welcome!*

---

**App-nexus** is a mod compatibility manager for **Skyrim Special Edition**.
It reads your mod list from **Mod Organizer 2**, queries the **Nexus Mods** API and
cross-references data with the **LOOT masterlist** to detect missing dependencies,
incompatibilities and warnings — all from a simple dark-themed GUI.

---

## Screenshot

> ![App-nexus screenshot](docs/screenshot.png)
>
> *(Replace this image with an actual screenshot of the application)*

---

## Features

- **Automatic Mod Organizer 2 reading**: detects instances, profiles, `modlist.txt`,
  `plugins.txt` and each mod's `meta.ini`.
- **Nexus Mods API queries**: fetches name, description, requirements and patches
  for each mod directly from Nexus.
- **Three-layer compatibility analysis**:
  - Missing requirements (needed mods that are not installed).
  - Incompatibilities detected by LOOT.
  - LOOT warnings and messages for individual plugins.
- **Fuzzy name matching** (82 % threshold) to pair mods even when they differ in
  version suffix or plugin extension (`.esp` / `.esm` / `.esl`).
- **Local SQLite cache** to avoid unnecessary API requests.
- **Tabbed detail panel**: Summary, Description (with BBCode cleanup) and
  Requirements table.
- **Compatibility report**: statistical summary with totals for mods, enabled mods,
  missing requirements and incompatibilities.
- **"Open on Nexus Mods" button** to jump straight to each mod's page.
- **Dark theme** powered by [sv-ttk](https://github.com/rdbende/Sun-Valley-ttk-theme).

---

## Installation

### Option A — Windows executable

1. Go to the [Releases](../../releases) section of this repository.
2. Download the `AppNexus.exe` file.
3. Run `AppNexus.exe` — no Python or dependency installation required.

### Option B — From source

Requires **Python 3.10+**.

```bash
# 1. Clone the repository
git clone https://github.com/FacundoSu1986/App-nexus.git
cd App-nexus

# 2. Install dependencies
pip install -r requirements.txt

# 3. Run the application
python main.py
```

> **Build the executable (optional):**
>
> ```bash
> pyinstaller build/app_nexus.spec
> ```
>
> The resulting file is generated at `dist/AppNexus.exe`.

---

## Step-by-step usage

1. **Get your Nexus Mods API Key** (see the next section).
2. **Open App-nexus** (`AppNexus.exe` or `python main.py`).
3. **Enter your API Key** in the corresponding toolbar field.
4. **Select the Mod Organizer 2 folder** using the MO2 path button.
5. **Choose the MO2 profile** you want to analyse.
6. **Press "Sync Nexus"** so that the application:
   - Reads the mod list and plugin load order from MO2.
   - Queries the Nexus Mods API for each mod.
   - Downloads and processes the LOOT masterlist.
   - Analyses compatibility and generates the report.
7. **Review the results**:
   - In the left panel, browse the mod list.
   - In the right panel, explore the *Summary*, *Description* and *Requirements* tabs.
   - In the bottom panel, check the compatibility report for missing dependencies,
     incompatibilities and warnings.

---

## How to get your Nexus Mods API Key

1. Log in to [nexusmods.com](https://www.nexusmods.com/).
2. Go to **My account → API tab**:
   <https://www.nexusmods.com/users/myaccount?tab=api>
3. Under **Personal API Key**, click **"Request an API Key"**.
4. Copy the generated key and paste it into App-nexus.

> The personal key is free and allows **100 requests per day**.

---

## Credits

- **Masterlist data**: provided by the
  [LOOT](https://loot.github.io/) project under the
  [CC BY-NC-SA 4.0](https://creativecommons.org/licenses/by-nc-sa/4.0/) licence.
- **Visual theme**: [Sun Valley ttk theme](https://github.com/rdbende/Sun-Valley-ttk-theme)
  by rdbende.

---

## Licence

This project is distributed under the **MIT** licence. See the [LICENSE](LICENSE)
file for details.
