"""Console Games page, ports manager.py's _build_games_console_page.
Backed entirely by sync_library.py (already non-GUI and tested) and
console_names.py, no new service module needed, this page just wires
those straight to a tree."""

from pathlib import Path, PurePosixPath
import re

import bridge.ui  # noqa: F401; import-time side effect: puts root/bridge/installer on sys.path

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMenu,
    QMessageBox,
    QPushButton,
    QTreeWidget,
    QTreeWidgetItem,
    QWidget,
)

import sync_library
from console_names import load_console_lookup, resolve_console_shortname
from bridge.ui.pages.base import PageBase
from bridge.ui.workers.task_runner import run_in_background
from shared.qt_theme import RED, TEXT_DIM

GAMES_CONSOLE_ALL_SYSTEMS = "All Systems"


class ConsoleBrowserPage(PageBase):
    def __init__(self, window, parent=None):
        super().__init__(parent, scrollable_body=False)
        self.window = window
        self._rows: list[dict] = []
        self._shortname_to_folder: dict[str, Path] = {}

        self.add_header(
            "Console Games",
            "Every game detected in your ROM library, grouped the same way syncing to the AVD does, "
            "a multi-disc game backed by an .m3u/.cue shows up here as one entry, not one per disc.",
        )

        search_row = QWidget()
        search_row_layout = QHBoxLayout(search_row)
        search_row_layout.setContentsMargins(0, 0, 0, 0)
        search_row_layout.addWidget(QLabel("Search:"))
        self.search_edit = QLineEdit()
        self.search_edit.textChanged.connect(self._render_filtered)
        search_row_layout.addWidget(self.search_edit, 1)
        search_row_layout.addWidget(QLabel("System:"))
        self.system_combo = QComboBox()
        self.system_combo.addItems([GAMES_CONSOLE_ALL_SYSTEMS])
        self.system_combo.currentTextChanged.connect(self._render_filtered)
        search_row_layout.addWidget(self.system_combo)
        self.count_label = QLabel("")
        self.count_label.setStyleSheet(f"color: {TEXT_DIM};")
        search_row_layout.addWidget(self.count_label)
        self.body_layout.addWidget(search_row)

        self.status_label = QLabel("Open this page to scan your ROM library.")
        self.status_label.setStyleSheet(f"color: {TEXT_DIM};")
        self.body_layout.addWidget(self.status_label)

        action_row = QWidget()
        action_row_layout = QHBoxLayout(action_row)
        action_row_layout.setContentsMargins(0, 0, 0, 0)
        rescan_button = QPushButton("Rescan")
        rescan_button.setObjectName("accent")
        rescan_button.clicked.connect(self.refresh)
        action_row_layout.addWidget(rescan_button)

        self.separate_button = QPushButton("Keep Discs Separate")
        self.separate_button.clicked.connect(self._add_exceptions)
        self.separate_button.setEnabled(False)
        action_row_layout.addWidget(self.separate_button)

        self.merge_button = QPushButton("Merge Discs Together")
        self.merge_button.clicked.connect(self._remove_exceptions)
        self.merge_button.setEnabled(False)
        action_row_layout.addWidget(self.merge_button)

        action_row_layout.addStretch(1)
        self.selection_hint = QLabel("Select rows to manage multi-disc games.")
        self.selection_hint.setStyleSheet(f"color: {TEXT_DIM};")
        action_row_layout.addWidget(self.selection_hint)
        self.body_layout.addWidget(action_row)

        note = QLabel(
            "Multi-disc playlists sync as one entry by default. Use \"Keep Discs Separate\"/\"Merge Discs Together\" "
            "above or in the right-click menu to manage multi-disc titles (details in the project README)."
        )
        note.setWordWrap(True)
        note.setStyleSheet(f"color: {TEXT_DIM};")
        self.body_layout.addWidget(note)

        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["Name", "Console", "Type", "File", "Discs kept separate"])
        self.tree.setRootIsDecorated(False)
        self.tree.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.tree.setColumnWidth(0, 220)
        self.tree.setColumnWidth(1, 90)
        self.tree.setColumnWidth(2, 160)
        self.tree.setColumnWidth(3, 260)
        self.tree.setColumnWidth(4, 140)
        self.tree.itemSelectionChanged.connect(self._update_selection_hint)
        self.tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self._show_context_menu)
        self.body_layout.addWidget(self.tree, 1)

        self._scan_signals = None

    def on_shown(self) -> None:
        self.refresh()

    def refresh(self) -> None:
        raw = self.window.config_data.get("roms_dir", "")
        if not raw or not Path(raw).is_dir():
            self._apply_scan([], "Set your ROM directory first.", True)
            return
        self.status_label.setText("Scanning...")
        self.status_label.setStyleSheet(f"color: {TEXT_DIM};")
        self._scan_signals = run_in_background(self._scan_worker, self._apply_scan_result, None, Path(raw))

    def _scan_worker(self, roms_dir: Path):
        try:
            exact, by_compact = load_console_lookup()
            exceptions = sync_library.load_dedupe_exceptions()
            consoles, skipped = sync_library.scan_library(roms_dir, exact, by_compact, dedupe_exceptions=exceptions)
        except OSError as e:
            return [], str(e), True, {}

        consoles.pop("windows", None)

        shortname_to_folder: dict[str, Path] = {}
        disc_to_parent_playlist: dict[str, str] = {}
        try:
            for console_folder in sorted(roms_dir.iterdir()):
                if console_folder.name in sync_library.IGNORE_TOP_LEVEL or not console_folder.is_dir():
                    continue
                shortname = resolve_console_shortname(console_folder.name, exact, by_compact)
                if shortname is None:
                    continue
                shortname_to_folder[shortname] = console_folder
                for pl_path in console_folder.rglob("*"):
                    suffix = pl_path.suffix.lower()
                    if suffix not in (".m3u", ".cue"):
                        continue
                    try:
                        rel_pl = pl_path.relative_to(console_folder).as_posix()
                    except ValueError:
                        continue
                    pl_key = f"{shortname}/{rel_pl}"
                    if suffix == ".m3u":
                        refs = sync_library._m3u_referenced_filenames(pl_path)
                    else:
                        refs = sync_library._cue_referenced_filenames(pl_path)
                    for ref in refs:
                        try:
                            disc_rel = (pl_path.parent / ref).relative_to(console_folder).as_posix()
                            disc_to_parent_playlist[f"{shortname}/{disc_rel}"] = pl_key
                        except ValueError:
                            continue
        except OSError:
            pass

        rows = []
        seen_keys = set()
        for shortname, entries in consoles.items():
            for rel, _size, _mtime in entries:
                exception_key = f"{shortname}/{rel}"
                seen_keys.add(exception_key)
                parent_playlist = disc_to_parent_playlist.get(exception_key)
                is_playlist = PurePosixPath(rel).suffix.lower() in (".m3u", ".cue")
                is_excepted = (exception_key in exceptions) or (parent_playlist in exceptions if parent_playlist else False)
                rows.append(
                    {
                        "shortname": shortname,
                        "rel": rel,
                        "name": PurePosixPath(rel).stem,
                        "is_playlist": is_playlist,
                        "exception_key": exception_key,
                        "parent_playlist": parent_playlist,
                        "excepted": is_excepted,
                        "hidden_from_iisu": False,
                    }
                )

        for exception_key in exceptions:
            if exception_key in seen_keys or "/" not in exception_key:
                continue
            shortname, _sep, rel = exception_key.partition("/")
            rows.append(
                {
                    "shortname": shortname,
                    "rel": rel,
                    "name": PurePosixPath(rel).stem,
                    "is_playlist": True,
                    "exception_key": exception_key,
                    "parent_playlist": None,
                    "excepted": True,
                    "hidden_from_iisu": True,
                }
            )

        rows.sort(key=lambda r: (r["shortname"], r["name"].casefold()))
        game_count = len({(r["shortname"], r["name"]) for r in rows if not r["hidden_from_iisu"]})
        status = f"{game_count} game(s) across {len(consoles)} console(s)"
        if skipped:
            status += f", {len(skipped)} folder(s) not recognized as a console"
        return rows, status, False, shortname_to_folder

    def _apply_scan_result(self, result) -> None:
        if len(result) == 4:
            rows, status, error, shortname_to_folder = result
            self._shortname_to_folder = shortname_to_folder
        else:
            rows, status, error = result
        self._apply_scan(rows, status, error)

    def _apply_scan(self, rows: list[dict], status: str, error: bool) -> None:
        self._rows = rows
        self.status_label.setText(status)
        self.status_label.setStyleSheet(f"color: {RED if error else TEXT_DIM};")
        current = self.system_combo.currentText()
        systems = [GAMES_CONSOLE_ALL_SYSTEMS] + sorted({row["shortname"] for row in rows})
        self.system_combo.blockSignals(True)
        self.system_combo.clear()
        self.system_combo.addItems(systems)
        self.system_combo.setCurrentText(current if current in systems else GAMES_CONSOLE_ALL_SYSTEMS)
        self.system_combo.blockSignals(False)
        self._render_filtered()

    def _render_filtered(self, *_args) -> None:
        self.tree.clear()
        query = self.search_edit.text().strip().casefold()
        system_filter = self.system_combo.currentText() or GAMES_CONSOLE_ALL_SYSTEMS
        for row in self._rows:
            if system_filter != GAMES_CONSOLE_ALL_SYSTEMS and row["shortname"] != system_filter:
                continue
            haystack = f"{row['name']} {row['shortname']} {row['rel']}".casefold()
            if query and query not in haystack:
                continue
            if row["hidden_from_iisu"]:
                type_label = "Playlist (hidden from iiSU)"
            elif row["is_playlist"]:
                type_label = "Playlist/Sheet"
            else:
                type_label = "File"
            item = QTreeWidgetItem([row["name"], row["shortname"], type_label, row["rel"], "Yes" if row["excepted"] else ""])
            item.setData(0, Qt.ItemDataRole.UserRole, row["exception_key"])
            if row["hidden_from_iisu"]:
                dim = QColor(TEXT_DIM)
                for col in range(5):
                    item.setForeground(col, dim)
            self.tree.addTopLevelItem(item)

        shown = self.tree.topLevelItemCount()
        total = len(self._rows)
        filtered = bool(query) or system_filter != GAMES_CONSOLE_ALL_SYSTEMS
        self.count_label.setText(f"{shown} shown / {total} total" if filtered else f"{total} entries")
        self._update_selection_hint()

    def _selected_rows(self) -> list[dict]:
        selected_keys = {item.data(0, Qt.ItemDataRole.UserRole) for item in self.tree.selectedItems()}
        return [row for row in self._rows if row["exception_key"] in selected_keys]

    def _can_keep_separate(self, selected: list[dict]) -> bool:
        return any(row.get("is_playlist") and not row.get("excepted") for row in selected)

    def _can_merge_together(self, selected: list[dict]) -> bool:
        if any(row.get("excepted") or row.get("parent_playlist") for row in selected):
            return True
        if len(selected) >= 2:
            return len({r["shortname"] for r in selected}) == 1
        return False

    def _update_selection_hint(self) -> None:
        selected = self._selected_rows()
        self.separate_button.setEnabled(self._can_keep_separate(selected))
        self.merge_button.setEnabled(self._can_merge_together(selected))
        if selected:
            self.selection_hint.setText(f"{len(selected)} selected, right-click or use buttons above.")
        else:
            self.selection_hint.setText("Select rows to manage multi-disc games.")

    def _show_context_menu(self, pos) -> None:
        item = self.tree.itemAt(pos)
        if item is None:
            return
        if item not in self.tree.selectedItems():
            self.tree.clearSelection()
            item.setSelected(True)
            self.tree.setCurrentItem(item)
            self._update_selection_hint()
        selected = self._selected_rows()
        if not selected:
            return

        menu = QMenu(self)
        keep_action = menu.addAction("Keep Discs Separate")
        keep_action.setEnabled(self._can_keep_separate(selected))
        merge_action = menu.addAction("Merge Discs Together")
        merge_action.setEnabled(self._can_merge_together(selected))
        chosen = menu.exec(self.tree.viewport().mapToGlobal(pos))
        if chosen == keep_action:
            self._add_exceptions()
        elif chosen == merge_action:
            self._remove_exceptions()

    def _add_exceptions(self) -> None:
        selected = [row for row in self._selected_rows() if row.get("is_playlist") and not row.get("excepted")]
        if not selected:
            QMessageBox.information(
                self,
                "Console Games",
                "Select one or more active playlist (.m3u) or sheet (.cue) entries to keep their discs separate.",
            )
            return
        exceptions = sync_library.load_dedupe_exceptions()
        exceptions.update(row["exception_key"] for row in selected)
        sync_library.save_dedupe_exceptions(exceptions)
        self.refresh()

    def _remove_exceptions(self) -> None:
        selected = self._selected_rows()
        if not selected:
            return

        exceptions = sync_library.load_dedupe_exceptions()
        keys_to_remove = set()
        for row in selected:
            if row.get("parent_playlist") and row["parent_playlist"] in exceptions:
                keys_to_remove.add(row["parent_playlist"])
            if row.get("excepted") and row.get("exception_key") in exceptions:
                keys_to_remove.add(row["exception_key"])

        if keys_to_remove:
            exceptions.difference_update(keys_to_remove)
            sync_library.save_dedupe_exceptions(exceptions)
            self.refresh()
            return

        disc_files = [row for row in selected if not row.get("is_playlist")]
        if len(disc_files) >= 2:
            self._create_m3u_from_files(disc_files)
            return

        QMessageBox.information(
            self,
            "Console Games",
            'Select entries marked "Discs kept separate" to merge them back, or select 2 or more disc files to create a playlist.',
        )

    def _create_m3u_from_files(self, disc_files: list[dict]) -> None:
        shortnames = {row["shortname"] for row in disc_files}
        if len(shortnames) > 1:
            QMessageBox.warning(self, "Console Games", "All selected disc files must belong to the same console.")
            return

        shortname = list(shortnames)[0]
        folder = self._shortname_to_folder.get(shortname)
        if not folder or not folder.is_dir():
            QMessageBox.warning(self, "Console Games", "Could not locate console folder on disk.")
            return

        file_paths = [folder / row["rel"] for row in disc_files]
        parent_dirs = {p.parent for p in file_paths}
        if len(parent_dirs) > 1:
            QMessageBox.warning(self, "Console Games", "All selected disc files must be in the same directory.")
            return

        target_dir = list(parent_dirs)[0]

        def _natural_sort_key(p: Path):
            return [int(text) if text.isdigit() else text.lower() for text in re.split(r"(\d+)", p.name)]

        sorted_files = sorted(file_paths, key=_natural_sort_key)

        first_stem = sorted_files[0].stem
        suggested_name = re.sub(
            r"[\s_]*[\(\[](?:disc|cd|disk)\s*\d+[\)\]].*$", "", first_stem, flags=re.IGNORECASE
        ).strip()
        if not suggested_name:
            suggested_name = first_stem

        playlist_name, ok = QInputDialog.getText(
            self,
            "Merge Discs into Playlist",
            f"Enter playlist (.m3u) name for {len(sorted_files)} discs:",
            text=suggested_name,
        )
        if not ok or not playlist_name.strip():
            return

        playlist_name = playlist_name.strip()
        if not playlist_name.lower().endswith(".m3u"):
            playlist_name += ".m3u"

        m3u_path = target_dir / playlist_name
        if m3u_path.exists():
            reply = QMessageBox.question(
                self,
                "Overwrite Existing Playlist?",
                f"'{playlist_name}' already exists. Overwrite it?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
                return

        try:
            content = "\n".join(p.name for p in sorted_files) + "\n"
            m3u_path.write_text(content, encoding="utf-8")
        except OSError as e:
            QMessageBox.critical(self, "Error", f"Failed to create playlist file:\n{e}")
            return

        rel_key = f"{shortname}/{m3u_path.relative_to(folder).as_posix()}"
        exceptions = sync_library.load_dedupe_exceptions()
        if rel_key in exceptions:
            exceptions.remove(rel_key)
            sync_library.save_dedupe_exceptions(exceptions)

        self.refresh()
