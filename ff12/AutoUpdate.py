import mobase
import shutil
import urllib.request
import json
import tempfile
import zipfile
import os
import socket

from PyQt6.QtCore import (
    QDateTime,
    qInfo,
    qWarning,
)
from PyQt6.QtWidgets import (
    QMessageBox,
    QApplication,
    QDialog,
    QVBoxLayout,
    QLabel,
    QTextBrowser,
    QDialogButtonBox,
    QMainWindow,
)
from PyQt6.QtCore import (
    QDateTime,
    pyqtSignal,
)
import sys

from .SettingsManager import settings_manager, SettingName
from .DateHelper import get_date_from_iso, get_date_time_from_iso

class FF12UpdateChecker:
    def __init__(self, repo_owner, repo_name, major, minor, patch, release_type, parent: QMainWindow = None):
        self.repo_owner = repo_owner
        self.repo_name = repo_name
        self.current_version = (major, minor, patch)
        self.release_type = release_type
        self.parentWindow = parent

    def _get_releases(self):
        url = f"https://api.github.com/repos/{self.repo_owner}/{self.repo_name}/releases"
        try:
            with urllib.request.urlopen(url, timeout=10) as response:
                data = response.read()
        except urllib.error.HTTPError as e:
            if e.code == 404:
                raise Exception(f"GitHub repository {self.repo_owner}/{self.repo_name} not found (404).")
            elif e.code == 403:
                raise Exception("GitHub API rate limit exceeded (403). Please try again later.")
            else:
                raise Exception(f"HTTP error occurred: {e.code} {e.reason}")
        except urllib.error.URLError as e:
            raise Exception(f"Network error: {e.reason}. Server unavailable or internet connection issue.")
        except socket.timeout:
            raise Exception("Connection timed out while trying to fetch releases.")

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
        if v2 is None:
            return True
        if v1 is None:
            return False
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

        for rel in releases:
            if not include_prerelease and rel.get('prerelease', False):
                continue
            tag = rel.get('tag_name', '')
            ver = self._parse_version(tag)
            if ver and self._is_newer(ver, self.current_version):
                if latest is None or self._is_newer(ver, self._parse_version(latest['tag_name'])):
                    latest = rel

        if latest:
            latest_ver = self._parse_version(latest.get('tag_name'))
            skip_ver = self._parse_version(skip_version)
            if not self._is_newer(latest_ver, skip_ver):
                self._log_skip_update()
            else:
                self._show_update_dialog(latest)
        else:
            self._log_no_update()

    def _collect_changelogs(self, latest_release):
        try:
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
                    changelogs.append((ver, tag, body, rel.get('published_at', '')))
            changelogs.sort(reverse=True)
            notes_md = ""
            for i, (ver, tag, body, published_at) in enumerate(changelogs):
                notes_md += f"## Changes in {tag} []()  Date: {get_date_from_iso(published_at)} ([commits](https://github.com/{self.repo_owner}/{self.repo_name}/commits/{tag}))\n{body}"
                if i < len(changelogs) - 1:
                    notes_md += "\n***\n"
                else:
                    notes_md += "\n"
            if not notes_md:
                notes_md = f"## Changes in {latest_release.get('tag_name', '')} []()  Date: {get_date_from_iso(latest_release.get('published_at', ''))} ([commits](https://github.com/{self.repo_owner}/{self.repo_name}/commits/{latest_release.get('tag_name', '')}))\n{latest_release.get('body', 'No patch notes.')}\n"
            return notes_md
        except Exception as e:
            qWarning(f"Failed to collect changelogs: {e}")
            return "## Error collecting changelogs\nAn error occurred while fetching the changelogs. Please check the log for details."

    def _create_update_dialog(self, notes_md, current_version, latest_tag, latest_date_str):
        class UpdateDialog(QDialog):
            skip_update = pyqtSignal()
            remind_later = pyqtSignal()
            def __init__(self, parent=None):
                super().__init__(parent)
                self.setWindowTitle("FF12 Plugin Update")
                self.setMinimumSize(500, 400)
                layout = QVBoxLayout(self)
                infoLabel = QLabel(f"A new version of FF12 MO2 Plugin is available!")
                infoLabel.setStyleSheet("font-weight: bold; font-size: 14pt;")
                layout.addWidget(infoLabel)
                versionLabel = QLabel(f"Current version: {current_version}\nNew version: {latest_tag} ({latest_date_str})\n\nPatch notes:")
                layout.addWidget(versionLabel)
                browser = QTextBrowser()
                browser.setMarkdown(notes_md)
                browser.setOpenExternalLinks(True)
                layout.addWidget(browser)
                button_box = QDialogButtonBox()
                update_btn = button_box.addButton("Update now", QDialogButtonBox.ButtonRole.AcceptRole)
                remind_btn = button_box.addButton("Remind me later", QDialogButtonBox.ButtonRole.DestructiveRole)
                skip_btn = button_box.addButton("Skip this version", QDialogButtonBox.ButtonRole.RejectRole)
                cancel_btn = button_box.addButton("Cancel", QDialogButtonBox.ButtonRole.RejectRole)
                layout.addWidget(button_box)
                update_btn.clicked.connect(self.accept)
                remind_btn.clicked.connect(self.remind_later.emit)
                skip_btn.clicked.connect(self.skip_update.emit)
                cancel_btn.clicked.connect(self.close)
        return UpdateDialog

    def _connect_update_dialog(self, dialog, latest_release, latest_tag):
        def on_accept():
            self._download_and_update(latest_release)
            dialog.close()
        def on_skip():
            settings_manager().set_setting(SettingName.SKIP_UPDATE_VERSION, latest_tag)
            dialog.close()
        def on_remind():
            remind_time = QDateTime.currentDateTime().addDays(1).toSecsSinceEpoch()
            settings_manager().set_setting(SettingName.SKIP_UPDATE_UNTIL_DATE, remind_time)
            dialog.close()
        dialog.accepted.connect(on_accept)
        dialog.skip_update.connect(on_skip)
        dialog.remind_later.connect(on_remind)

    def _show_update_dialog(self, latest_release):
        notes_md = self._collect_changelogs(latest_release)
        current_version = f"v{self.current_version[0]}.{self.current_version[1]}.{self.current_version[2]}"
        latest_tag = latest_release.get('tag_name', '')
        latest_date_str = get_date_time_from_iso(latest_release.get('published_at', ''))
        app = QApplication.instance() or QApplication(sys.argv)
        UpdateDialog = self._create_update_dialog(notes_md, current_version, latest_tag, latest_date_str)
        dialog = UpdateDialog(parent=self.parentWindow)
        dialog.activateWindow()
        dialog.raise_()
        self._connect_update_dialog(dialog, latest_release, latest_tag)
        dialog.show()

    def _log_no_update(self):
        qInfo("No updates available for FF12 Plugin.")
    
    def _log_skip_update(self):
        qInfo("Skipped update for FF12 Plugin.")

    def _download_and_update(self, release):
        asset = self._find_zip_asset(release)
        if not asset:
            self._show_error("No zip asset found in release.")
            return
        tmpdir = tempfile.mkdtemp()
        zip_path = os.path.join(tmpdir, asset['name'])
        try:
            self._download_asset(asset['browser_download_url'], zip_path)
            new_script, ff12_update_dir = self._extract_update_files(zip_path, tmpdir)
            if not new_script:
                self._show_error("game_ff12.py not found in update package.")
                return
            self._replace_plugin_files(new_script, ff12_update_dir)
            self._show_restart_dialog()
        except Exception as e:
            self._show_error(f"Update failed: {e}")
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)

    def _find_zip_asset(self, release):
        for a in release.get('assets', []):
            if a.get('name', '').endswith('.zip'):
                return a
        return None

    def _download_asset(self, url, zip_path):
        with urllib.request.urlopen(url) as response, open(zip_path, 'wb') as out_file:
            shutil.copyfileobj(response, out_file)

    def _extract_update_files(self, zip_path, tmpdir):
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            zip_ref.extractall(tmpdir)
        new_script = None
        ff12_update_dir = None
        for root, dirs, files in os.walk(tmpdir):
            if 'game_ff12.py' in files:
                new_script = os.path.join(root, 'game_ff12.py')
            if 'ff12' in dirs:
                ff12_update_dir = os.path.join(root, 'ff12')
        return new_script, ff12_update_dir

    def _replace_plugin_files(self, new_script, ff12_update_dir):
        plugin_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        main_plugin_path = os.path.join(plugin_dir, 'game_ff12.py')
        shutil.copy2(new_script, main_plugin_path)
        ff12_plugin_dir = os.path.join(plugin_dir, 'ff12')
        if os.path.isdir(ff12_plugin_dir):
            shutil.rmtree(ff12_plugin_dir, ignore_errors=True)
        if ff12_update_dir and os.path.isdir(ff12_update_dir):
            shutil.copytree(ff12_update_dir, ff12_plugin_dir)

    def _show_error(self, msg):
        app = QApplication.instance() or QApplication(sys.argv)
        QMessageBox.critical(None, "FF12 Plugin Update", msg)

    def _show_restart_dialog(self):
        app = QApplication.instance() or QApplication(sys.argv)
        QMessageBox.information(None, "FF12 Plugin Update", "Update complete! Please restart Mod Organizer 2 for changes to take effect.")
