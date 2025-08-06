import mobase
VERSION_MAJOR = 0
VERSION_MINOR = 4
VERSION_PATCH = 0
VERSION_RELEASE_TYPE = mobase.ReleaseType.BETA
import shutil # needed by update checker and for getting cmd.exe path

from collections.abc import Mapping
from enum import StrEnum
from pathlib import Path

from PyQt6.QtCore import (
    QDateTime,
    QDir,
    QFileInfo,
    QStandardPaths,
    qInfo,
)

from ..basic_features import (
    BasicLocalSavegames,
    BasicModDataChecker,
    GlobPatterns,
)
from ..basic_features.utils import is_directory

from ..basic_features.basic_save_game_info import (
    BasicGameSaveGame,
    BasicGameSaveGameInfo,
    format_date,
)

from ..basic_game import BasicGame

from ..steam_utils import find_steam_path
import vdf

# Imports needed for update checking
import urllib.request
import json
import tempfile
import zipfile
import os
from PyQt6.QtWidgets import (
    QMessageBox,
    QApplication,
    QDialog,
    QVBoxLayout,
    QLabel,
    QTextBrowser,
    QDialogButtonBox,
    QMainWindow
)
from PyQt6.QtCore import (
    Qt,
    QDateTime
)
import sys

class FF12UpdateChecker:
    def __init__(self, repo_owner, repo_name, major, minor, patch, release_type):
        self.repo_owner = repo_owner
        self.repo_name = repo_name
        self.current_version = (major, minor, patch)
        self.release_type = release_type

    def _get_releases(self):
        url = f"https://api.github.com/repos/{self.repo_owner}/{self.repo_name}/releases"
        with urllib.request.urlopen(url) as response:
            data = response.read()
        releases = json.loads(data)
        return releases

    def _parse_version(self, tag):
        # Handles tags like v1.2.3, 1.2.3, v1.2.3-suffix, 1.2.3-suffix
        tag = tag.lstrip('v')
        # Remove any suffix after patch number before checking version
        main_part = tag.split('-')[0]
        parts = main_part.split('.')
        if len(parts) < 3:
            return None
        try:
            return tuple(int(p) for p in parts[:3])
        except Exception:
            return None

    def _is_newer(self, v1, v2):
        return v1 > v2

    def check_for_update(self):
        # GitHub API has 60 requests per hour limit for unauthenticated requests.
        # So let's not make a big fuss about it and handle errors gracefully.
        try:
            releases = self._get_releases()
        except Exception as e:
            qInfo(f"Failed to fetch releases: {e}")
            return
        include_prerelease = self.release_type != mobase.ReleaseType.FINAL
        latest = None
        skip_version = settings_manager().get_setting(SettingName.SKIP_UPDATE_VERSION)

        qInfo(f"Skip version: {skip_version}")

        for rel in releases:
            if not include_prerelease and rel.get('prerelease', False):
                continue
            tag = rel.get('tag_name', '')
            ver = self._parse_version(tag)
            if ver and self._is_newer(ver, self.current_version):
                if latest is None or self._is_newer(ver, self._parse_version(latest['tag_name'])):
                    latest = rel
    
        if latest and latest.get('tag_name') != skip_version:
            self._show_update_dialog(latest)
        else:
            self._log_no_update()

    def _show_update_dialog(self, latest_release):
        # Gather all releases newer than current_version
        all_releases = self._get_releases()
        include_prerelease = self.release_type != mobase.ReleaseType.FINAL
        current_ver = self.current_version
        changelogs = []
        for rel in all_releases:
            if not include_prerelease and rel.get('prerelease', False):
                continue
            tag = rel.get('tag_name', '')
            ver = self._parse_version(tag)
            if ver and self._is_newer(ver, current_ver):
                body = rel.get('body', 'No patch notes.')
                changelogs.append((ver, tag, body))
        # Sort newest to oldest
        changelogs.sort(reverse=True)
        # Build markdown
        notes_md = ""
        for i, (ver, tag, body) in enumerate(changelogs):
            notes_md += f"## Changes in {tag}\n{body}"
            if i < len(changelogs) - 1:
                notes_md += "\n***\n"
            else:
                notes_md += "\n"
        # If no changelogs found, fallback to latest
        if not notes_md:
            notes_md = f"## Changes in {latest_release.get('tag_name', '')}\n{latest_release.get('body', 'No patch notes.')}\n"
        current_version = f"v{self.current_version[0]}.{self.current_version[1]}.{self.current_version[2]}"
        latest_tag = latest_release.get('tag_name', '')
        app = QApplication.instance() or QApplication(sys.argv)

        class UpdateDialog(QDialog):
            def __init__(self, parent=None):
                super().__init__(parent)
                self.setWindowTitle("FF12 Plugin Update")
                self.setMinimumSize(500, 400)
                layout = QVBoxLayout(self)
                infoLabel = QLabel(f"A new version of FF12 MO2 Plugin is available!")
                infoLabel.setStyleSheet("font-weight: bold; font-size: 14pt;")
                layout.addWidget(infoLabel)
                versionLabel = QLabel(f"Current version: {current_version}\nNew version: {latest_tag}\n\nPatch notes:")
                layout.addWidget(versionLabel)
                browser = QTextBrowser()
                browser.setMarkdown(notes_md)
                browser.setOpenExternalLinks(True)
                layout.addWidget(browser)
                button_box = QDialogButtonBox()
                yes_btn = button_box.addButton("Update now", QDialogButtonBox.ButtonRole.AcceptRole)
                no_btn = button_box.addButton("Remind me later", QDialogButtonBox.ButtonRole.DestructiveRole)
                skip_btn = button_box.addButton("Skip this version", QDialogButtonBox.ButtonRole.RejectRole)
                cancel_btn = button_box.addButton("Cancel", QDialogButtonBox.ButtonRole.RejectRole)
                layout.addWidget(button_box)
                yes_btn.clicked.connect(self.accept)
                no_btn.clicked.connect(self._remind_later)
                skip_btn.clicked.connect(self._skip_version)
                cancel_btn.clicked.connect(self._cancel)
                self._action = None

            def _cancel(self):
                self._action = "cancel"
                self.reject()

            def _remind_later(self):
                self._action = "remind"
                self.reject()

            def _skip_version(self):
                self._action = "skip"
                self.reject()

        dialog = UpdateDialog()
        dialog.setWindowModality(Qt.WindowModality.ApplicationModal)
        dialog.setWindowFlags(dialog.windowFlags() | Qt.WindowType.WindowStaysOnTopHint)
        dialog.activateWindow()
        dialog.raise_()
        result = dialog.exec()

        if result == QDialog.DialogCode.Accepted:
            self._download_and_update(latest_release)
        elif getattr(dialog, "_action", None) == "skip":
            settings_manager().set_setting(SettingName.SKIP_UPDATE_VERSION, latest_tag)
        elif getattr(dialog, "_action", None) == "remind":
            # Save remind date (now + 1 day)
            remind_time = QDateTime.currentDateTime().addDays(1).toSecsSinceEpoch()
            settings_manager().set_setting(SettingName.SKIP_UPDATE_UNTIL_DATE, remind_time)

    def _log_no_update(self):
        qInfo("No updates available for FF12 Plugin.")

    def _download_and_update(self, release):
        asset = None
        for a in release.get('assets', []):
            if a.get('name', '').endswith('.zip'):
                asset = a
                break
        if not asset:
            self._show_error("No zip asset found in release.")
            return
        url = asset['browser_download_url']
        tmpdir = tempfile.mkdtemp()
        zip_path = os.path.join(tmpdir, asset['name'])
        try:
            with urllib.request.urlopen(url) as response, open(zip_path, 'wb') as out_file:
                shutil.copyfileobj(response, out_file)
            with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                zip_ref.extractall(tmpdir)
            # Find game_ff12.py in extracted files
            new_script = None
            for root, dirs, files in os.walk(tmpdir):
                if 'game_ff12.py' in files:
                    new_script = os.path.join(root, 'game_ff12.py')
                    break
            if not new_script:
                self._show_error("game_ff12.py not found in update package.")
                return
            # Replace current script
            current_script = os.path.abspath(__file__)
            shutil.copy2(new_script, current_script)
            self._show_restart_dialog()
        except Exception as e:
            self._show_error(f"Update failed: {e}")
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)

    def _show_error(self, msg):
        app = QApplication.instance() or QApplication(sys.argv)
        QMessageBox.critical(None, "FF12 Plugin Update", msg)

    def _show_restart_dialog(self):
        app = QApplication.instance() or QApplication(sys.argv)
        QMessageBox.information(None, "FF12 Plugin Update", "Update complete! Please restart Mod Organizer 2 for changes to take effect.")

class SettingsManager:
    _instance = None

    def __init__(self, organizer: mobase.IOrganizer, game_name: str):
        self._organizer = organizer
        self._game_name = game_name
        SettingsManager._instance = self

    @staticmethod
    def get_instance():
        if SettingsManager._instance is None:
            raise RuntimeError("SettingsManager not initialized.")
        return SettingsManager._instance

    def get_setting(self, key: str):
        return self._organizer.pluginSetting(self._game_name, key)

    def set_setting(self, key: str, value):
        self._organizer.setPluginSetting(self._game_name, key, value)

def settings_manager():
    return SettingsManager.get_instance()

class FF12ModDataChecker(BasicModDataChecker):
    def __init__(self, organizer: mobase.IOrganizer, plugin_name: str):
        self._organizer = organizer
        self._plugin_name = plugin_name

        super().__init__(
            GlobPatterns(
                unfold=['*'],
                delete=["*"],
                valid=["x64", "mods", "dxgi.dll", "dinput8.dll", "launcher.dll"],
                move={"scripts":        "x64/",
                      "modules":        "x64/",
                      "gamedata":       "mods/deploy/ff12data/",
                      "jsondata":       "mods/deploy/ff12data/",
                      "prefetchdata":   "mods/deploy/ff12data/",
                      "ps2data":        "mods/deploy/ff12data/",
                      "ff12data":       "mods/deploy/",
                      },
            )
        )

    def dataLooksValid(
        self, filetree: mobase.IFileTree
    ) -> mobase.ModDataChecker.CheckReturn:
        status = mobase.ModDataChecker.VALID

        rp = self._regex_patterns
        for entry in filetree:
            name = entry.name().casefold()

            if rp.valid.match(name):
                if status is mobase.ModDataChecker.INVALID:
                    status = mobase.ModDataChecker.VALID

            elif rp.move_match(name) is not None:
                status = mobase.ModDataChecker.FIXABLE

            elif rp.unfold.match(name) and is_directory(entry):
                status = mobase.ModDataChecker.FIXABLE
                new_status = self.dataLooksValid(entry)
                if new_status is not mobase.ModDataChecker.VALID:
                    status = new_status

            elif rp.delete.match(name) is not None:
                status = mobase.ModDataChecker.FIXABLE

            else:
                status = mobase.ModDataChecker.INVALID
                break
        return status

    def fix(self, filetree: mobase.IFileTree) -> mobase.IFileTree:
        rp = self._regex_patterns

        for entry in list(filetree):
            name = entry.name().casefold()

            if rp.valid.match(name):
                continue

            elif (move_key := rp.move_match(name)) is not None:
                target = self._file_patterns.move[move_key]
                filetree.move(entry, target)

            elif rp.unfold.match(name) and is_directory(entry):
                filetree.merge(entry)
                entry.detach()
                self.fix(filetree)

            elif rp.delete.match(name):
                entry.detach()

        return filetree

class FF12SaveGame(BasicGameSaveGame):
    def __init__(self, filepath: Path):
        super().__init__(filepath)
        f_stat = self._filepath.stat()
        self._size = f_stat.st_size
        self._created = f_stat.st_birthtime
        self._modified = f_stat.st_mtime

    def getName(self) -> str:
        return f"Slot {self.getSlot()}"

    def getSaveGroupIdentifier(self) -> str:
        return "Default"

    def getSlot(self) -> str:
        return int(self._filepath.stem[6:9])

    def getSize(self) -> int:
        return self._size

    def getBirthTime(self) -> QDateTime:
        return QDateTime.fromSecsSinceEpoch(int(self._created))

    def getCreationTime(self) -> QDateTime:
        return QDateTime.fromSecsSinceEpoch(int(self._modified))

def getSaveMetadata(savepath: Path, save: mobase.ISaveGame) -> Mapping[str, str]:
    assert isinstance(save, FF12SaveGame)
    return {
        "Slot": save.getSlot(),
        "Size": f"{save.getSize() / 1024:.2f} KB",
        "Created At": format_date(save.getBirthTime()),
        "Last Saved": format_date(save.getCreationTime())
    }

class SettingName(StrEnum):
    AUTO_STEAM_ID = "autoSteamId"
    STEAM_ID_64 = "steamId64"
    DISABLE_AUTO_UPDATES = "disableAutoUpdates"
    SKIP_UPDATE_VERSION = "skipUpdateVersion"
    SKIP_UPDATE_UNTIL_DATE = "skipUpdateUntilDate"

class FF12TZAGame(BasicGame):
    Name = "Final Fantasy XII TZA Support Plugin"
    Author = "ffgriever & Xeavin"
    GameName = "Final Fantasy XII The Zodiac Age"
    GameShortName = "finalfantasy12"
    GameNexusName = "finalfantasy12"
    GameBinary = "x64/FFXII_TZA.exe"
    GameDataPath = "%GAME_PATH%"
    GameSteamId = 595520
    GameSavesDirectory = "%GAME_DOCUMENTS%"

    def __init__(self):
        super().__init__()
        self._suppress_setting_callback = False

    def init(self, organizer: mobase.IOrganizer) -> bool:
        super().init(organizer)
        SettingsManager(organizer, self.name())
        self._register_feature(FF12ModDataChecker(self._organizer, self.name()))
        self._register_feature(BasicLocalSavegames(self.savesDirectory()))
        self._register_feature(BasicGameSaveGameInfo(get_metadata = getSaveMetadata))
        organizer.onPluginSettingChanged(self._on_plugin_setting_changed_callback)
        organizer.onUserInterfaceInitialized(self._on_user_interface_initialized_callback)

        auto_steam_id = settings_manager().get_setting(SettingName.AUTO_STEAM_ID)
        if auto_steam_id is True:
            self._set_last_logged_steam_id()

        return True

    def version(self):
        return mobase.VersionInfo(
            VERSION_MAJOR,
            VERSION_MINOR,
            VERSION_PATCH,
            VERSION_RELEASE_TYPE
        )

    def settings(self) -> list[mobase.PluginSetting]:
        return [
            mobase.PluginSetting(
                SettingName.AUTO_STEAM_ID,
                (
                    f"If true, automatically set '{SettingName.STEAM_ID_64}' to last logged Steam user."
                ),
                default_value = True,
            ),
            mobase.PluginSetting(
                SettingName.STEAM_ID_64,
                (
                    "Unique 64-bit Steam user identifier used to locate saves and configuration files. "
                    "Leave empty when launching the game without Steam."
                ),
                default_value = "",
            ),
            mobase.PluginSetting(
                SettingName.DISABLE_AUTO_UPDATES,
                (
                    "If true, disables automatic updates for the plugin."
                ),
                default_value = False,
            ),
            mobase.PluginSetting(
                SettingName.SKIP_UPDATE_VERSION,
                (
                    "If set, skips update dialog for this version."
                ),
                default_value = "v0.0.0",
            ),
            mobase.PluginSetting(
                SettingName.SKIP_UPDATE_UNTIL_DATE,
                (
                    "If set, skips update dialog until this date (in seconds since epoch)."
                ),
                default_value = 0,
            ),
        ]

    def documentsDirectory(self) -> QDir:
        docs_path = QDir(
            QDir(
                QStandardPaths.writableLocation(QStandardPaths.StandardLocation.DocumentsLocation)
            ).filePath("My Games/FINAL FANTASY XII THE ZODIAC AGE")
        )

        steam_id = settings_manager().get_setting(SettingName.STEAM_ID_64)
        if steam_id:
            docs_path = QDir(docs_path.absoluteFilePath(steam_id))

        return docs_path

    def executables(self):
            # Windows isn't necessarily installed in "C:\Windows\".
            cmd_path = shutil.which('cmd.exe')

            # We're using cmd.exe to launch a launcher, because otherwise it can't be accessed
            # using VFS. Otherwise we would have to scan mods and detect where it actually is.
            default_launcher_path = self.gameDirectory().absoluteFilePath("x64/ff12-launcher.exe")

            # If launcher exists, run it, else set color to red and show message.
            launcher_cmd = (
                f'if exist "{default_launcher_path}" '
                f'("{default_launcher_path}") '
                f'else (color 0C && echo Launcher not found: "{default_launcher_path}". && echo Please install External File Loader with MO2 support. && pause && color)'
            )

            return [
                mobase.ExecutableInfo(
                    f"{self.gameName()} (Modded)",
                    QFileInfo(cmd_path)
                ).withArgument(f'/c {launcher_cmd}').withWorkingDirectory(self.gameDirectory().absoluteFilePath("x64")),
                mobase.ExecutableInfo(
                    f"{self.gameName()} (Vanilla)",
                    QFileInfo(self.gameDirectory().absoluteFilePath(self.binaryName())),
                ),
                mobase.ExecutableInfo(
                    "Configuration Tool",
                    QFileInfo(self.gameDirectory().absoluteFilePath("x64/FFXII_TZA_GameSetting.exe")),
                ),
                mobase.ExecutableInfo(
                    "Reload VFS",
                    QFileInfo(cmd_path)
                ).withArgument(f'/c'),
            ]

    def iniFiles(self):
        return [
            "GameSetting.ini",
            "keymap.ini"
        ]

    def listSaves(self, folder: QDir) -> list[mobase.ISaveGame]:
        return [
            FF12SaveGame(path)
            for path in Path(folder.absolutePath()).glob("FFXII_???")
            if path.is_file() and path.name[6:9].isdigit()
        ]

    def _on_plugin_setting_changed_callback(
        self,
        plugin_name: str,
        setting: str,
        old: mobase.MoVariant,
        new: mobase.MoVariant,
    ):
        if plugin_name != self.name() or self._suppress_setting_callback is True:
            return

        if setting == SettingName.AUTO_STEAM_ID and old is False and new is True:
            self._suppress_setting_callback = True
            try:
                self._set_last_logged_steam_id()
            finally:
                self._suppress_setting_callback = False
        elif setting == SettingName.STEAM_ID_64 and old != new:
            if settings_manager().get_setting(SettingName.AUTO_STEAM_ID) is True:
                self._suppress_setting_callback = True
                try:
                    settings_manager().set_setting(SettingName.AUTO_STEAM_ID, False)
                finally:
                    self._suppress_setting_callback = False

    def _get_last_logged_steam_id(self) -> str | None:
        steam_path = find_steam_path()
        if not steam_path:
            return None

        loginusers_path = steam_path / "config" / "loginusers.vdf"
        try:
            with open(loginusers_path, "r", encoding = "utf-8") as f:
                data = vdf.load(f)

            users = data.get("users", {})
            for steam_id, info in users.items():
                if info.get("MostRecent") == "1":
                    return steam_id

            if users:
                return next(iter(users))
        except Exception:
            return None

    def _set_last_logged_steam_id(self):
        last_steam_id = self._get_last_logged_steam_id()
        if not last_steam_id:
            return

        cur_steam_id = settings_manager().get_setting(SettingName.STEAM_ID_64)
        if last_steam_id == cur_steam_id:
            return

        settings_manager().set_setting(SettingName.STEAM_ID_64, last_steam_id)
        if cur_steam_id:
            qInfo(f"Updated Steam ID from '{cur_steam_id}' to '{last_steam_id}'.")
        else:
            qInfo(f"Set Steam ID to '{last_steam_id}'.")
    
    def _on_user_interface_initialized_callback(
            self,
            window: QMainWindow
    ):
        current_game = self._organizer.managedGame()
        if current_game is not self:
            return
        
        if settings_manager().get_setting(SettingName.DISABLE_AUTO_UPDATES) is not True:

            remind_time = settings_manager().get_setting(SettingName.SKIP_UPDATE_UNTIL_DATE)
            now_secs = int(QDateTime.currentDateTime().toSecsSinceEpoch())

            if remind_time and now_secs is not None and remind_time > now_secs:
                return

            update_checker = FF12UpdateChecker(
                "FF12-Modding", "FF12-MO2-Plugin",
                VERSION_MAJOR, VERSION_MINOR, VERSION_PATCH,
                VERSION_RELEASE_TYPE
            )
            update_checker.check_for_update()
    
