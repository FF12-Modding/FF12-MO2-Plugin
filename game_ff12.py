import mobase
import shutil
import os

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

    def _set_setting(self, key: str, value: mobase.MoVariant):
        self._organizer.setPluginSetting(self._plugin_name, key, value)

    def _check_mod_for_launcher(self, filetree: mobase.IFileTree):
        modlist = self._organizer.modList()
        qInfo(f"Searching for launcher in {filetree.name()}")
        mod = modlist.getMod(filetree.name())
        if not mod or mod.isForeign() or mod.isBackup() or mod.isSeparator():
            return

        path = self._find_launcher_path(filetree)
        if path != "":
            qInfo(f"Found launcher at {mod.absolutePath()}/{path}")
            self._set_setting("launcher_path", os.path.join(mod.absolutePath(), path))
        return

    def _find_launcher_path(self, filetree: mobase.IFileTree) -> str:
        path = ""
        for entry in filetree:
            if is_directory(entry):
                path = self._find_launcher_path(entry)
                continue

            if not is_directory(entry) and entry.name().casefold() == "ff12-launcher.exe":
                return entry.path()

        return path

    def dataLooksValid(
        self, filetree: mobase.IFileTree
    ) -> mobase.ModDataChecker.CheckReturn:
        status = mobase.ModDataChecker.VALID

        self._check_mod_for_launcher(filetree)
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
        self._register_feature(FF12ModDataChecker(self._organizer, self.name()))
        self._register_feature(BasicLocalSavegames(self.savesDirectory()))
        self._register_feature(BasicGameSaveGameInfo(get_metadata = getSaveMetadata))
        organizer.onPluginSettingChanged(self._on_plugin_setting_changed_callback)

        auto_steam_id = self._get_setting(SettingName.AUTO_STEAM_ID)
        if auto_steam_id is True:
            self._set_last_logged_steam_id()

        return True

    def version(self):
        return mobase.VersionInfo(0, 2, 0, mobase.ReleaseType.BETA)

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
                "launcher_path",
                (
                    "Path which contains the launcher."
                    "Updates whenever you install a mod containing it."
                ),
                default_value="",
            )
        ]

    def _get_setting(self, key: str) -> mobase.MoVariant:
        return self._organizer.pluginSetting(self.name(), key)

    def _set_setting(self, key: str, value: mobase.MoVariant):
        self._organizer.setPluginSetting(self.name(), key, value)

    def documentsDirectory(self) -> QDir:
        docs_path = QDir(
            QDir(
                QStandardPaths.writableLocation(QStandardPaths.StandardLocation.DocumentsLocation)
            ).filePath("My Games/FINAL FANTASY XII THE ZODIAC AGE")
        )

        steam_id = self._get_setting(SettingName.STEAM_ID_64)
        if steam_id:
            docs_path = QDir(docs_path.absoluteFilePath(steam_id))

        return docs_path

    def executables(self):
            launcher_path = self._get_setting("launcher_path")
            if not launcher_path:
                launcher_path = self.gameDirectory().absoluteFilePath("x64/ff12-launcher.exe")
            # Windows isn't necessarily installed in "C:\Windows\".
            cmd_path = shutil.which('cmd.exe')

            return [
                mobase.ExecutableInfo(
                    f"{self.gameName()} Launcher",
                    QFileInfo(launcher_path),
                ),
                mobase.ExecutableInfo(
                    f"{self.gameName()}",
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
            if self._get_setting(SettingName.AUTO_STEAM_ID) is True:
                self._suppress_setting_callback = True
                try:
                    self._set_setting(SettingName.AUTO_STEAM_ID, False)
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

        cur_steam_id = self._get_setting(SettingName.STEAM_ID_64)
        if last_steam_id == cur_steam_id:
            return

        self._set_setting(SettingName.STEAM_ID_64, last_steam_id)
        if cur_steam_id:
            qInfo(f"Updated Steam ID from '{cur_steam_id}' to '{last_steam_id}'.")
        else:
            qInfo(f"Set Steam ID to '{last_steam_id}'.")
