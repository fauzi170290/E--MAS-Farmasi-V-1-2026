from __future__ import annotations

import hashlib
from pathlib import Path

from PySide6.QtCore import QObject, Signal
from PySide6.QtNetwork import QLocalServer, QLocalSocket


_PROCESS_GUARDS: dict[str, "SingleInstanceGuard"] = {}


class SingleInstanceGuard(QObject):
    activation_requested = Signal()

    def __init__(self, data_dir: Path) -> None:
        super().__init__()
        digest = hashlib.sha256(
            str(data_dir.resolve()).casefold().encode("utf-8")
        ).hexdigest()[:20]
        self.server_name = f"emss-farmasi-{digest}"
        self.server = QLocalServer(self)
        self.server.newConnection.connect(self._receive_connections)
        self._owns_server = False

    def acquire(self) -> bool:
        existing = _PROCESS_GUARDS.get(self.server_name)
        if existing is not None and existing._owns_server:
            existing.activation_requested.emit()
            return False
        probe = QLocalSocket()
        probe.connectToServer(self.server_name)
        if probe.waitForConnected(250):
            probe.write(b"ACTIVATE")
            probe.flush()
            probe.waitForBytesWritten(250)
            probe.disconnectFromServer()
            return False
        probe.abort()
        QLocalServer.removeServer(self.server_name)
        self._owns_server = self.server.listen(self.server_name)
        if self._owns_server:
            _PROCESS_GUARDS[self.server_name] = self
        return self._owns_server

    def close(self) -> None:
        if self._owns_server:
            self.server.close()
            QLocalServer.removeServer(self.server_name)
            self._owns_server = False
            if _PROCESS_GUARDS.get(self.server_name) is self:
                del _PROCESS_GUARDS[self.server_name]

    def _receive_connections(self) -> None:
        while self.server.hasPendingConnections():
            socket = self.server.nextPendingConnection()
            if socket is None:
                continue
            socket.waitForReadyRead(100)
            message = bytes(socket.readAll())
            socket.disconnectFromServer()
            socket.deleteLater()
            if message == b"ACTIVATE":
                self.activation_requested.emit()
