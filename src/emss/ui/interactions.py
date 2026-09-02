"""Small, centralized hover feedback for the desktop interface.

Qt stylesheets do not animate, so this module keeps the visual transition in
one place.  A graphics effect does not change a widget's geometry: panels and
their existing spacing remain exactly as designed.
"""
from __future__ import annotations

from PySide6.QtCore import (
    QAbstractAnimation,
    QEasingCurve,
    QEvent,
    QObject,
    QParallelAnimationGroup,
    QPropertyAnimation,
    Qt,
)
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractButton,
    QAbstractItemView,
    QGraphicsDropShadowEffect,
    QWidget,
)


HOVER_DURATION_MS = 180


class HoverFeedbackController(QObject):
    """Apply restrained pointer and elevation feedback to clickable controls."""

    def __init__(self, root: QWidget) -> None:
        super().__init__(root)
        self._animations: dict[QAbstractButton, QParallelAnimationGroup] = {}
        for button in root.findChildren(QAbstractButton):
            self._install_button(button)
        for view in root.findChildren(QAbstractItemView):
            # Rows are actionable in the queue, history, and navigation.  The
            # cursor is limited to the item viewport and does not alter layout.
            view.viewport().setCursor(Qt.CursorShape.PointingHandCursor)

    def _install_button(self, button: QAbstractButton) -> None:
        if button.property("emssHoverFeedback"):
            return
        button.setProperty("emssHoverFeedback", True)
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        effect = QGraphicsDropShadowEffect(button)
        effect.setColor(QColor(15, 23, 42, 0))
        effect.setBlurRadius(0.0)
        effect.setOffset(0.0, 0.0)
        button.setGraphicsEffect(effect)
        button.installEventFilter(self)

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        if isinstance(watched, QAbstractButton):
            if event.type() == QEvent.Type.Enter and watched.isEnabled():
                self._animate(watched, elevate=True)
            elif event.type() in (QEvent.Type.Leave, QEvent.Type.EnabledChange):
                self._animate(watched, elevate=False)
        return super().eventFilter(watched, event)

    def _animate(self, button: QAbstractButton, *, elevate: bool) -> None:
        effect = button.graphicsEffect()
        if not isinstance(effect, QGraphicsDropShadowEffect):
            return
        prior = self._animations.pop(button, None)
        if prior is not None:
            prior.stop()
            prior.deleteLater()
        group = QParallelAnimationGroup(button)
        blur = QPropertyAnimation(effect, b"blurRadius", group)
        blur.setDuration(HOVER_DURATION_MS)
        blur.setEasingCurve(QEasingCurve.Type.OutCubic)
        blur.setStartValue(effect.blurRadius())
        blur.setEndValue(12.0 if elevate else 0.0)
        color = QPropertyAnimation(effect, b"color", group)
        color.setDuration(HOVER_DURATION_MS)
        color.setEasingCurve(QEasingCurve.Type.OutCubic)
        color.setStartValue(effect.color())
        color.setEndValue(
            QColor(15, 23, 42, 52) if elevate else QColor(15, 23, 42, 0)
        )
        group.addAnimation(blur)
        group.addAnimation(color)
        group.finished.connect(lambda: self._animations.pop(button, None))
        self._animations[button] = group
        group.start(QAbstractAnimation.DeletionPolicy.DeleteWhenStopped)


def install_hover_feedback(root: QWidget) -> HoverFeedbackController:
    """Install one controller and retain it for the lifetime of ``root``."""
    controller = root.findChild(HoverFeedbackController, "emssHoverFeedback")
    if controller is None:
        controller = HoverFeedbackController(root)
        controller.setObjectName("emssHoverFeedback")
    return controller
