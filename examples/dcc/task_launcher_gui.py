"""Minimal PySide6 task launcher for the Pipeline Production Hub API.

Provides a small desktop UI inspired by ShotGrid Create / Flow Production
Tracking / ftrack Connect: log in, browse projects and shots, pick a pipeline
task, choose a file, and publish it through the same workflow used by the
``artist_publish.py`` / ``nuke_publish.py`` / ``maya_publish.py`` /
``houdini_publish.py`` examples.

Run with::

    pip install -e ".[dcc-gui]"
    python examples/dcc/task_launcher_gui.py
"""

from __future__ import annotations

import sys
import traceback
from pathlib import Path
from typing import Any

THIS_DIR = Path(__file__).resolve().parent
if str(THIS_DIR) not in sys.path:
    sys.path.insert(0, str(THIS_DIR))

try:
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import (
        QApplication,
        QComboBox,
        QFileDialog,
        QFormLayout,
        QHBoxLayout,
        QLabel,
        QLineEdit,
        QListWidget,
        QListWidgetItem,
        QMainWindow,
        QMessageBox,
        QPlainTextEdit,
        QPushButton,
        QStatusBar,
        QVBoxLayout,
        QWidget,
    )
except ImportError as exc:  # pragma: no cover - GUI optional dependency
    raise SystemExit(
        'task_launcher_gui requires PySide6. Install with: pip install -e ".[dcc-gui]"'
    ) from exc

from _api import ApiError, PipelineApiClient  # noqa: E402
from _workflow import PublishRequest, run_publish  # noqa: E402

DEFAULT_BASE_URL = "http://localhost:8000"


class TaskLauncherWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Pipeline Production Hub - Task Launcher")
        self.resize(820, 560)

        self._client: PipelineApiClient | None = None
        self._projects: list[dict[str, Any]] = []
        self._shots: list[dict[str, Any]] = []
        self._tasks: list[dict[str, Any]] = []

        self._build_ui()
        self.statusBar().showMessage("Not connected.")

    # ── UI construction ─────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        central = QWidget(self)
        layout = QVBoxLayout(central)

        login_form = QFormLayout()
        self.base_url_edit = QLineEdit(DEFAULT_BASE_URL)
        self.email_edit = QLineEdit()
        self.email_edit.setPlaceholderText("admin@vfxhub.dev")
        self.password_edit = QLineEdit()
        self.password_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.password_edit.setPlaceholderText("admin123")
        self.login_button = QPushButton("Log in")
        self.login_button.clicked.connect(self._on_login_clicked)

        login_form.addRow("Base URL", self.base_url_edit)
        login_form.addRow("Email", self.email_edit)
        login_form.addRow("Password", self.password_edit)
        login_form.addRow("", self.login_button)
        layout.addLayout(login_form)

        selection_layout = QHBoxLayout()

        project_box = QVBoxLayout()
        project_box.addWidget(QLabel("Project"))
        self.project_combo = QComboBox()
        self.project_combo.setEnabled(False)
        self.project_combo.currentIndexChanged.connect(self._on_project_changed)
        project_box.addWidget(self.project_combo)
        selection_layout.addLayout(project_box, 1)

        shot_box = QVBoxLayout()
        shot_box.addWidget(QLabel("Shot"))
        self.shot_combo = QComboBox()
        self.shot_combo.setEnabled(False)
        self.shot_combo.currentIndexChanged.connect(self._on_shot_changed)
        shot_box.addWidget(self.shot_combo)
        selection_layout.addLayout(shot_box, 1)

        layout.addLayout(selection_layout)

        layout.addWidget(QLabel("Pipeline tasks"))
        self.task_list = QListWidget()
        self.task_list.itemSelectionChanged.connect(self._refresh_publish_state)
        layout.addWidget(self.task_list, 2)

        publish_row = QHBoxLayout()
        self.file_edit = QLineEdit()
        self.file_edit.setPlaceholderText("Pick a file to publish ...")
        self.file_edit.textChanged.connect(self._refresh_publish_state)
        self.browse_button = QPushButton("Browse ...")
        self.browse_button.clicked.connect(self._on_browse_clicked)
        self.publish_button = QPushButton("Publish")
        self.publish_button.setEnabled(False)
        self.publish_button.clicked.connect(self._on_publish_clicked)
        publish_row.addWidget(self.file_edit, 3)
        publish_row.addWidget(self.browse_button)
        publish_row.addWidget(self.publish_button)
        layout.addLayout(publish_row)

        layout.addWidget(QLabel("Activity log"))
        self.log_view = QPlainTextEdit()
        self.log_view.setReadOnly(True)
        layout.addWidget(self.log_view, 2)

        self.setCentralWidget(central)
        self.setStatusBar(QStatusBar(self))

    # ── Helpers ────────────────────────────────────────────────────────────

    def _log(self, message: str) -> None:
        self.log_view.appendPlainText(message)

    def _set_busy(self, busy: bool) -> None:
        cursor = Qt.CursorShape.WaitCursor if busy else Qt.CursorShape.ArrowCursor
        self.setCursor(cursor)
        QApplication.processEvents()

    def _selected_task(self) -> dict[str, Any] | None:
        items = self.task_list.selectedItems()
        if not items:
            return None
        index = self.task_list.row(items[0])
        if 0 <= index < len(self._tasks):
            return self._tasks[index]
        return None

    def _refresh_publish_state(self) -> None:
        has_task = self._selected_task() is not None
        has_file = bool(self.file_edit.text().strip())
        self.publish_button.setEnabled(has_task and has_file and self._client is not None)

    # ── Slots ──────────────────────────────────────────────────────────────

    def _on_login_clicked(self) -> None:
        base_url = self.base_url_edit.text().strip() or DEFAULT_BASE_URL
        email = self.email_edit.text().strip()
        password = self.password_edit.text()

        if not email or not password:
            QMessageBox.warning(self, "Missing credentials", "Email and password are required.")
            return

        self._set_busy(True)
        try:
            if self._client is not None:
                self._client.close()
            self._client = PipelineApiClient(base_url)
            self._client.login(email, password)
            user = self._client.get_me()
            self._log(f"Logged in as {user['email']} ({base_url}).")
            self.statusBar().showMessage(f"Connected as {user['email']}")
            self._load_projects()
        except (ApiError, RuntimeError) as exc:
            self._show_error("Login failed", exc)
        finally:
            self._set_busy(False)

    def _load_projects(self) -> None:
        assert self._client is not None
        self._projects = self._client.list_projects()
        self.project_combo.blockSignals(True)
        self.project_combo.clear()
        for project in self._projects:
            label = f"{project.get('code', '')} - {project.get('name', '')}".strip(" -")
            self.project_combo.addItem(label, userData=project["id"])
        self.project_combo.blockSignals(False)
        self.project_combo.setEnabled(bool(self._projects))
        if self._projects:
            self._on_project_changed(0)
        else:
            self._log("No projects accessible to this user.")

    def _on_project_changed(self, _index: int) -> None:
        if self._client is None or self.project_combo.currentIndex() < 0:
            return
        project_id = str(self.project_combo.currentData())
        try:
            self._set_busy(True)
            self._shots = self._client.list_project_shots(project_id)
            self.shot_combo.blockSignals(True)
            self.shot_combo.clear()
            for shot in self._shots:
                label = f"{shot.get('code', '')} - {shot.get('name', '')}".strip(" -")
                self.shot_combo.addItem(label, userData=shot["id"])
            self.shot_combo.blockSignals(False)
            self.shot_combo.setEnabled(bool(self._shots))
            if self._shots:
                self._on_shot_changed(0)
            else:
                self.task_list.clear()
                self._tasks = []
                self._log("Project has no shots.")
        except ApiError as exc:
            self._show_error("Failed to load shots", exc)
        finally:
            self._set_busy(False)
            self._refresh_publish_state()

    def _on_shot_changed(self, _index: int) -> None:
        if self._client is None or self.shot_combo.currentIndex() < 0:
            return
        shot_id = str(self.shot_combo.currentData())
        try:
            self._set_busy(True)
            self._tasks = self._client.list_shot_tasks(shot_id)
            self.task_list.clear()
            for task in self._tasks:
                label = (
                    f"{task.get('step_name', '?')} "
                    f"[{task.get('step_type', '?')}] "
                    f"- {task.get('status', '?')}"
                )
                self.task_list.addItem(QListWidgetItem(label))
            if not self._tasks:
                self._log("Shot has no pipeline tasks. Create one via the API or seed first.")
        except ApiError as exc:
            self._show_error("Failed to load tasks", exc)
        finally:
            self._set_busy(False)
            self._refresh_publish_state()

    def _on_browse_clicked(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Pick a file to publish")
        if path:
            self.file_edit.setText(path)

    def _on_publish_clicked(self) -> None:
        task = self._selected_task()
        file_path = Path(self.file_edit.text().strip())
        if task is None or not file_path.exists() or self._client is None:
            return

        request = PublishRequest(
            task_id=str(task["id"]),
            primary_file=file_path,
            description=f"GUI publish of {file_path.name}",
            source_label="Task Launcher GUI",
        )

        try:
            self._set_busy(True)
            result = run_publish(self._client, request, notify=self._log)
            self._log(f"OK - version {result.version['code']} ({result.version['id']})")
            self.statusBar().showMessage(f"Published version {result.version['code']}")
        except (ApiError, FileNotFoundError, RuntimeError, ValueError) as exc:
            self._show_error("Publish failed", exc)
        finally:
            self._set_busy(False)

    def _show_error(self, title: str, exc: Exception) -> None:
        self._log(f"ERROR - {title}: {exc}")
        traceback.print_exc()
        QMessageBox.critical(self, title, str(exc))

    def closeEvent(self, event: Any) -> None:
        if self._client is not None:
            self._client.close()
        super().closeEvent(event)


def main() -> int:
    app = QApplication(sys.argv)
    window = TaskLauncherWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
