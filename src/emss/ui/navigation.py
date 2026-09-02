"""Grouped navigation around existing pages; retains the tab API for alert routing."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout, QLabel, QTabWidget, QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget, QStyle, QScrollArea, QGridLayout
from emss.ui.icons import clinical_icon, navigation_icon_key


class ActionLayout(QGridLayout):
    """Two columns keep administrative action labels reachable at 1280px."""
    def addWidget(self, widget, *args):
        index = self.count()
        super().addWidget(widget, index // 2, index % 2)

    def addStretch(self, *args):
        pass


class ScrollableTabs(QTabWidget):
    def addTab(self, page, title):
        page.setObjectName('workflowPage')
        page.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        page.setStyleSheet('QWidget#workflowPage { background: #F4F7FA; }')
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        scroll.setWidget(page)
        return super().addTab(scroll, title)

    def widget(self, index):
        scroll = super().widget(index)
        return scroll.widget() if scroll is not None else None

    def currentWidget(self):
        return self.widget(self.currentIndex())

    def indexOf(self, page):
        for i in range(self.count()):
            if self.widget(i) is page:
                return i
        return -1

    def setCurrentWidget(self, page):
        index = self.indexOf(page)
        if index >= 0:
            self.setCurrentIndex(index)


class WorkflowNavigation(QWidget):
    def __init__(self, tabs: QTabWidget, parent=None):
        super().__init__(parent)
        self.tabs = tabs
        tabs.tabBar().hide()
        self.tree = QTreeWidget()
        self.tree.setObjectName('workflowNavigation')
        self.tree.setHeaderHidden(True)
        self.tree.setRootIsDecorated(False)
        self.tree.setIndentation(12)
        self.tree.setFixedWidth(230)
        self.tree.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.tree.setStyleSheet('QTreeWidget {background: #FFFFFF; border: 1px solid #CBD5E1;} '
            'QTreeWidget::item {height: 32px; padding: 2px;} '
            'QTreeWidget::item:selected {background: #DBEAFE; color: #123B5D;}')
        self.groups = {}
        self.destinations = {}
        self.heading = QLabel()
        self.heading.setObjectName('workflowHeading')
        self.heading.setStyleSheet('font-size: 15pt; font-weight: 700; padding: 4px; color: #123B5D;')
        body = QVBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.addWidget(self.heading)
        body.addWidget(tabs, 1)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.tree)
        layout.addLayout(body, 1)
        self.tree.currentItemChanged.connect(self._selected)
        tabs.currentChanged.connect(self._tab_changed)

    def add(self, group, title, page, callback=None):
        if group not in self.groups:
            item = QTreeWidgetItem(self.tree, [group])
            item.setFlags(Qt.ItemFlag.ItemIsEnabled)
            font = item.font(0); font.setBold(True); item.setFont(0, font)
            item.setExpanded(True)
            self.groups[group] = item
        item = QTreeWidgetItem(self.groups[group], [title])
        item.setToolTip(0, title)
        icon = QStyle.StandardPixmap.SP_FileDialogDetailedView
        if group == 'Pengaturan': icon = QStyle.StandardPixmap.SP_FileDialogInfoView
        item.setIcon(0, clinical_icon(
            navigation_icon_key(title), self.style().standardIcon(icon)
        ))
        key = len(self.destinations)
        item.setData(0, Qt.ItemDataRole.UserRole, key)
        self.destinations[key] = (page, callback)
        return item

    def _selected(self, item, previous):
        if item is None:
            return
        destination = self.destinations.get(item.data(0, Qt.ItemDataRole.UserRole))
        if destination is None:
            return
        page, callback = destination
        self.tabs.blockSignals(True)
        self.tabs.setCurrentWidget(page)
        self.tabs.blockSignals(False)
        self.heading.setText(item.text(0))
        if callback:
            callback()

    def _tab_changed(self, index):
        page = self.tabs.widget(index)
        current = self.tree.currentItem()
        if current and self.destinations.get(current.data(0, Qt.ItemDataRole.UserRole), (None,))[0] is page:
            return
        for group in self.groups.values():
            for n in range(group.childCount()):
                item = group.child(n)
                if self.destinations[item.data(0, Qt.ItemDataRole.UserRole)][0] is page:
                    self.tree.setCurrentItem(item)
                    return
