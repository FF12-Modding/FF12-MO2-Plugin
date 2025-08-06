import mobase
from enum import StrEnum

class SettingName(StrEnum):
    AUTO_STEAM_ID = "autoSteamId"
    STEAM_ID_64 = "steamId64"
    DISABLE_AUTO_UPDATES = "disableAutoUpdates"
    SKIP_UPDATE_VERSION = "skipUpdateVersion"
    SKIP_UPDATE_UNTIL_DATE = "skipUpdateUntilDate"

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