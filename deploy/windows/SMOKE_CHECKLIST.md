# Pechepro v0.1 - Smoke Checklist (20 scenarios)

> **Target environment:** clean Windows 11 22H2 VM (recommended: Hyper-V or
> VirtualBox snapshot). Standard user account (not Administrator). No prior
> Pechepro install present.

> **Test artifact:** `dist/pechepro-setup.exe` produced by
> `deploy\windows\build.ps1` (local) or downloaded from a GitHub release.

> **Pass criteria:** all 20 scenarios green. Any FAIL blocks the release.
> Mark each checkbox `[x]` once verified, with date + tester initials in the
> Sign-off table.

---

## Pre-test setup

1. Take a VM snapshot named `clean-win11-pre-pechepro`.
2. Copy `pechepro-setup.exe` into the VM (shared folder, USB, or download
   inside the VM).
3. Optional: install uBlock Origin in Edge for scenario 11.
4. Optional: install DB Browser for SQLite for scenarios 13 and 17.

After all scenarios are run, **revert the VM** to the clean snapshot.

---

## Scenarios

### 1. Fresh install on Windows 11 22H2 - no admin needed

- **Steps:**
  1. Log in as a standard (non-administrator) user.
  2. Right-click `pechepro-setup.exe` and choose **Open** (do not
     "Run as administrator").
  3. Walk through the wizard: accept the licence, leave default options,
     click **Install**.
- **Expected:** Installer runs without a UAC prompt. Final page displays
  the "Launch Pechepro" checkbox. `%LOCALAPPDATA%\Programs\pechepro\pechepro.exe`
  exists after install.
- **Status:** [ ]

### 2. Launch from Start Menu shortcut

- **Steps:**
  1. Close the installer (uncheck "Launch Pechepro" so the launch comes
     from the shortcut).
  2. Press the Windows key, type **Pechepro**, press Enter.
  3. Wait up to 5 seconds for the window to appear.
- **Expected:** PyWebView window opens within 5 seconds on first launch
  (one-file PyInstaller bootstrap unpacks to `%TEMP%`). No console window
  visible. Task Manager shows a single `pechepro.exe` process.
- **Status:** [ ]

### 3. Launch from Desktop shortcut (if created during install)

- **Steps:**
  1. Verify a "Pechepro" icon exists on the Desktop (assumes the
     desktop-icon Task was checked during install).
  2. Close any running Pechepro instance.
  3. Double-click the Desktop icon.
- **Expected:** App launches. Subsequent launches (cache warm) appear in
  under 2 seconds.
- **Status:** [ ]

### 4. First-run DB initialization

- **Steps:**
  1. Before launching Pechepro for the very first time, confirm
     `%LOCALAPPDATA%\pechepro\pechepro.db` does **not** exist
     (`Test-Path "$env:LOCALAPPDATA\pechepro\pechepro.db"` returns `False`).
  2. Launch Pechepro and wait for the Home screen to render.
  3. Exit the app cleanly via the window close button.
- **Expected:** `%LOCALAPPDATA%\pechepro\pechepro.db` is created. File size
  is at least 50 KB (schema + seed). No error dialogs.
- **Status:** [ ]

### 5. Home screen renders - 15 species, 65+ regions, 5 water types

- **Steps:**
  1. Launch Pechepro.
  2. Open the species dropdown and count the entries.
  3. Open the region dropdown and confirm grouping by country (CA / US).
  4. Open the water-type dropdown.
- **Expected:** Species dropdown shows exactly **15** entries. Region
  dropdown lists **65 or more** entries grouped by country. Water-type
  dropdown shows **5** options (lac, riviere, etang, reservoir, marais).
  No "loading..." stuck state on any dropdown.
- **Status:** [ ]

### 6. GPS auto-detection - Windows Location prompt accepted

- **Steps:**
  1. On the Home screen, click **Detecter ma position**.
  2. Accept the Windows Location consent dialog if it appears.
  3. Wait up to 5 seconds for the lat/lon fields to populate.
- **Expected:** Lat and Lon fields populate with non-zero values (4
  decimals). The region dropdown auto-selects the nearest known region
  (e.g., Quebec for Levis).
- **Status:** [ ]

### 7. GPS denied - manual region selection works

- **Steps:**
  1. Open Settings -> Privacy & Security -> Location and toggle
     **Location services OFF**.
  2. Relaunch Pechepro.
  3. Click **Detecter ma position** and observe the response.
  4. Manually select **Quebec** from the region dropdown.
- **Expected:** A polite "Localisation non disponible - veuillez choisir
  manuellement" message is displayed. Manual region selection works; no
  crash. Re-enable Location services after the test.
- **Status:** [ ]

### 8. Walleye / Levis QC / lac / midday -> Conditions screen < 3 sec

- **Steps:**
  1. On Home, pick species **Dore jaune (Walleye)**, region **Quebec**
     (Levis), water type **lac**.
  2. Use the local clock at solar midday for the date of the test.
  3. Click **Voir les conditions** and time the render.
- **Expected:** Conditions screen renders in under 3 seconds. Page
  displays the weather block (temp + wind + baro trend), sun-rise/set,
  current moon phase, solunar major + minor periods, and at least 5
  ranked tips. Page contains the word "Dore" or "Walleye".
- **Status:** [ ]

### 9. Tips screen - at least 5 tips, ranked, source URLs clickable

- **Steps:**
  1. From the Conditions screen, click the **Astuces** tab.
  2. Scroll through the list of tips.
  3. Click a source URL on one of the tips.
- **Expected:** Five or more tip cards visible, ranked by confidence
  score. Each tip displays a source URL as a clickable link. At least 3
  distinct source domains visible across the page (e.g., Sepaq, Quebec
  Peche, In-Fisherman, Bassmaster, INFOpeche). Clicked link opens in the
  default browser.
- **Status:** [ ]

### 10. Expedia widget loads (online) - leaderboard 728x90 visible

- **Steps:**
  1. With normal network connectivity, open the Tips screen.
  2. Scroll to the page footer and wait up to 3 seconds for async load.
  3. If PyWebView dev tools are enabled (debug build), inspect the
     network panel.
- **Expected:** An Expedia leaderboard banner (728 x 90) renders at the
  page footer. When inspecting the DOM, the widget element carries
  `data-camref="1101l5IQud"` and `data-pubref="pechepro-tips"`.
- **Status:** [ ]

### 11. Expedia widget gracefully absent (uBlock or offline)

- **Steps:**
  1. Either (a) install uBlock Origin in Edge and enable a banner
     blocklist, or (b) disconnect the VM from the network.
  2. Relaunch Pechepro and navigate to the Tips screen.
- **Expected:** Tips render normally. The Expedia banner slot is empty:
  no error message, no broken-image placeholder, no layout collapse
  beyond the banner's reserved height. The rest of the page remains
  legible.
- **Status:** [ ]

### 12. Offline mode - tips served from local DB after relaunch

- **Steps:**
  1. Close Pechepro completely (verify in Task Manager).
  2. Disconnect WiFi / Ethernet.
  3. Relaunch Pechepro and pick **Dore + Quebec + lac** -> Conditions.
- **Expected:** Sun/moon times displayed (local astronomical calc).
  Solunar windows displayed. Tips list rendered from local SQLite. No
  network error dialog. Conditions screen reachable within 3 seconds.
  At least 5 tips visible.
- **Status:** [ ]

### 13. "Meteo indisponible" banner when offline + cache expired > 1 h

- **Steps:**
  1. Continue from scenario 12 (still offline).
  2. Open `%LOCALAPPDATA%\pechepro\pechepro.db` in DB Browser for SQLite.
  3. In the `weather_cache` table, set `expires_at` for the current
     cache_key to a date in 2020.
  4. Save and relaunch Pechepro. Re-render the Conditions screen.
- **Expected:** A yellow banner reading "Meteo indisponible - astuces
  basees sur les conditions de reference" replaces the weather block.
  Tips remain available. No silent failure or stack-trace dialog.
- **Status:** [ ]

### 14. Language switch FR <-> EN - UI and tips update

- **Steps:**
  1. With the app open in FR, toggle the language switcher in the header
     to EN.
  2. Reload the Tips screen if it does not refresh automatically.
  3. Toggle back to FR.
- **Expected:** All visible UI strings switch to English (header, labels,
  buttons). Tip text switches from `tip_text_fr` to `tip_text_en`.
  Species names switch (Dore -> Walleye, etc.). No mixed-language strings
  on the same screen. Toggling back restores French text.
- **Status:** [ ]

### 15. Sun/moon times correct - cross-check against suncalc.org for Levis QC

- **Steps:**
  1. With Conditions screen open for **Levis, QC** (lat 46.81, lon -71.21)
     on today's date, note the displayed sunrise, sunset, moonrise,
     and moonset times.
  2. Open `https://www.suncalc.org/` in a browser, enter the same
     coordinates and date.
  3. Compare each value pair.
- **Expected:** All four times match (within +/- 2 minutes). Solar noon
  also consistent.
- **Status:** [ ]

### 16. Solunar windows visualized - major + minor periods with scores

- **Steps:**
  1. On the Conditions screen, scroll to the **Periodes solunaires**
     section.
  2. Note the major and minor periods displayed.
- **Expected:** Two **major** periods (~2 h each) and two **minor**
  periods (~1 h each) displayed for the day, with times in 24h format.
  A quality score (1-10) is shown next to each period. No overlap. All
  times fit within 00:00-23:59.
- **Status:** [ ]

### 17. Baro trend rising/falling indicator - verify against Open-Meteo

- **Steps:**
  1. With normal connectivity, render the Conditions screen and note the
     baro-trend indicator (up arrow = rising, down arrow = falling, flat
     bar = stable).
  2. Cross-check against the 6-hour pressure trend from
     `https://open-meteo.com/` for the same lat/lon.
  3. Optional: edit `weather_cache.payload_json` in `pechepro.db` to
     fake a pressure drop (e.g., 1020 -> 1010 hPa) and reload; confirm
     the indicator flips.
- **Expected:** Indicator direction matches Open-Meteo's 6 h trend.
  Faked drop flips the indicator from rising to falling on reload.
- **Status:** [ ]

### 18. Sync curated data on launch (within 24 h of upstream edit)

- **Steps:**
  1. On a dev machine, edit `data/curated/tips.csv` on `main` (add a new
     row with a distinctive `tip_text_fr` and `tip_text_en`) and push.
  2. Verify the new content is reachable at
     `https://raw.githubusercontent.com/sxc3030-eng/pechepro/main/data/curated/tips.csv`.
  3. On the VM, force-expire the sync cache by setting
     `data_sync_meta.last_synced_at` for `tips` to zero (DB Browser).
  4. Close + relaunch Pechepro with network.
- **Expected:** At launch, the new tip row is fetched and inserted into
  the SQLite `tips` table. A SQL query against `pechepro.db` finds the
  new tip's `id` / `tip_text_fr`. The new tip appears in the ranking
  when conditions match. Revert the test edit on `main` after the test.
- **Status:** [ ]

### 19. Uninstaller - Pechepro removed, user data policy documented

- **Steps:**
  1. Open Settings -> Apps -> Installed apps.
  2. Find **Pechepro**, click **Uninstall**, confirm the prompt.
  3. After the uninstaller closes, verify removal:
     - `%LOCALAPPDATA%\Programs\pechepro\` is gone.
     - Desktop + Start Menu shortcuts are removed.
     - Apps & Features no longer lists Pechepro.
- **Expected:** All four removals confirmed. **User data policy:** by
  design, `%LOCALAPPDATA%\pechepro\` (containing `pechepro.db`) is
  **left intact** so reinstall restores user preferences. Users who
  want a full wipe must delete `%LOCALAPPDATA%\pechepro\` manually -
  this is documented in README.md and CHANGELOG.md.
- **Status:** [ ]

### 20. Reinstall after uninstall - clean state restored

- **Steps:**
  1. Run `pechepro-setup.exe` again on the same VM (post-uninstall).
  2. Complete the wizard.
  3. Launch Pechepro.
- **Expected:** Install succeeds without errors. App launches.
  Because `%LOCALAPPDATA%\pechepro\pechepro.db` was preserved (see
  scenario 19), the previously saved last-species, last-region, and
  language preference are restored. No "first-run" wizard re-shown.
  No schema-migration errors in `%TEMP%\pechepro.log` (if present).
- **Status:** [ ]

---

## Antivirus & SmartScreen sanity

Before sign-off, also verify the following on a Windows 11 VM with
Defender enabled (real-time protection ON):

- [ ] Defender does **not** flag `pechepro-setup.exe` as a threat at
      download or scan time.
- [ ] SmartScreen warning text is the standard "Windows protected your
      PC - Unknown publisher" - clicking **More info** -> **Run anyway**
      proceeds the install. (V0.2 will eliminate this with a code-signing
      certificate.)
- [ ] `pechepro.exe` (the inner exe) does **not** trigger a Defender
      block when launched.
- [ ] Optional: scan `pechepro-setup.exe` on
      [VirusTotal](https://www.virustotal.com/). Goal: under 5/70 engines
      flagging (acceptable noise from heuristics on PyInstaller binaries).

---

## Sign-off

| Field          | Value         |
|----------------|---------------|
| Build version  | `___________` |
| Tester         | `___________` |
| VM image       | `___________` |
| Date           | `___________` |
| Result         | [ ] PASS / [ ] FAIL |
| Notes          | `___________` |

If FAIL: do **not** publish the GitHub release. Open an issue per
failed scenario and fix before re-tagging.
