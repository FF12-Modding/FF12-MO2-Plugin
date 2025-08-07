# Final Fantasy XII Game Plugin for Mod Organizer 2

A simple plugin for Mod Organizer 2 that enables mod management for Final Fantasy XII.

**Requirement:**
This plugin requires the [FF12 External File Loader](https://www.nexusmods.com/finalfantasy12/mods/170?tab=files) (installed in launcher mode) to work properly.

## Features
- Enables mod management for FF12 in MO2
- Automatic launcher handling
- Automatic update checking on each start
- Support for saves and ini files

## Installation
1. Make sure Mod Organizer 2 (MO2) is closed.
2. Open your MO2 installation directory.
3. Navigate to `📁plugins` → `📁basic_games` → `📁games`.
4. *(Optional)* If an `📁ff12` directory exists there, delete it.
5. From the zip archive, copy the `📄game_ff12.py` file and the `📁ff12` directory into this location, replacing any previous versions.
6. Start MO2.
7. Create a new instance using this plugin.
8. The plugin will check for updates each time MO2 starts.

## Automatic Updates
When the update window appears in the new MO2 plugin, you have four options:
- **Update now** – Installs the update immediately.
- **Remind me later** – Postpones the update reminder for 24 hours.
- **Skip this version** – Ignores this update until a newer version is released.
- **Cancel** – Dismisses the update for now; you will be prompted again the next time MO2 starts.

## Plugin Options
The plugin provides several configurable options. To access them, click the tools icon in MO2, go to the Plugins tab, and select the FF12 plugin:
- **autoSteamId** – If enabled, automatically retrieves your last used Steam user ID. Disable this if you want to set your own ID manually.
- **steamId64** – Your Steam user ID (used for saves and ini files). You can leave it on auto, or enter it manually (which disables auto detection).
- **disableAutoUpdates** – If set to true, completely disables automatic updates.
- **skipUpdateUntilDate** – A timestamp (seconds since epoch) that determines when the plugin will prompt for updates again. Not typically user-modified, but if you clicked "Remind me later" by accident, set this to zero to re-enable update prompts on next restart.
- **skipUpdateVersion** – Set if you used "Skip this version". If you clicked this by accident, leave this setting blank or set it to the default `v0.0.0` to allow updates again on next restart.
