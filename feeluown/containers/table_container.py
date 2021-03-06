import asyncio
import logging

from PyQt5.QtCore import Qt, QSize
from PyQt5.QtGui import QImage, QPixmap, QFont, QPalette, QPainter, QColor
from PyQt5.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListView,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QTabBar,
    QVBoxLayout,
    QWidget,
)

from fuocore import ModelType
from feeluown.helpers import use_mac_theme
from feeluown.components.songs_table import SongsTableModel, SongsTableView


logger = logging.getLogger(__name__)


class DescriptionContainer(QScrollArea):
    def __init__(self, parent=None):
        super().__init__(parent)

        self._label = QLabel(self)
        self._label.setWordWrap(True)
        self._label.setTextFormat(Qt.RichText)
        self._label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.setWidget(self._label)
        self.setWidgetResizable(True)

        self.setFrameShape(QFrame.NoFrame)
        self._label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(0)

    @property
    def html(self):
        return self._label.text()

    def set_html(self, desc):
        self._label.setText(desc)

    def keyPressEvent(self, event):
        key_code = event.key()
        if key_code == Qt.Key_J:
            value = self.verticalScrollBar().value()
            self.verticalScrollBar().setValue(value + 20)
        elif key_code == Qt.Key_K:
            value = self.verticalScrollBar().value()
            self.verticalScrollBar().setValue(value - 20)
        else:
            super().keyPressEvent(event)


class TableOverview(QFrame):
    def __init__(self, parent):
        super().__init__(parent)

        self._height = 180
        self.cover_label = QLabel(self)
        self._desc_container = DescriptionContainer(self)

        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Maximum)
        self._layout = QHBoxLayout(self)
        self._left_sub_layout = QVBoxLayout()
        self._right_sub_layout = QVBoxLayout()

        self._right_sub_layout.addWidget(self._desc_container)
        self._left_sub_layout.addWidget(self.cover_label)
        self._left_sub_layout.addStretch(0)
        self._layout.addLayout(self._left_sub_layout)
        self._layout.addSpacing(20)
        self._layout.addLayout(self._right_sub_layout)
        self._layout.setStretch(1, 1)
        self.cover_label.setFixedWidth(200)
        self.setFixedHeight(self._height)

    def set_cover(self, pixmap):
        self.cover_label.setPixmap(
            pixmap.scaledToWidth(self.cover_label.width(),
                                 mode=Qt.SmoothTransformation))

    def set_desc(self, desc):
        self._desc_container.show()
        self._desc_container.set_html(desc)

    def keyPressEvent(self, event):
        key_code = event.key()
        if key_code == Qt.Key_Space:
            if self._height < 300:
                self._height = 300
                self.setMinimumHeight(self._height)
                self.setMaximumHeight(self._height)
            else:
                self._height = 180
                self.setMinimumHeight(self._height)
                self.setMaximumHeight(self._height)
            event.accept()


class SongsTableContainer(QFrame):
    def __init__(self, app, parent=None):
        super().__init__(parent)
        self._app = app

        self.songs_table = SongsTableView(self)
        self.table_overview = TableOverview(self)

        self._layout = QVBoxLayout(self)

        self.setAutoFillBackground(False)
        if use_mac_theme():
            self._layout.setContentsMargins(0, 0, 0, 0)
            self._layout.setSpacing(0)
        self._layout.addWidget(self.table_overview)
        self._layout.addWidget(self.songs_table)

        self.songs_table.play_song_needed.connect(
            lambda song: asyncio.ensure_future(self.play_song(song)))
        self.songs_table.show_artist_needed.connect(
            lambda artist: asyncio.ensure_future(self.show_model(artist)))
        self.songs_table.show_album_needed.connect(
            lambda album: asyncio.ensure_future(self.show_model(album)))
        self._cover_pixmap = None
        self.hide()

    async def play_song(self, song):
        loop = asyncio.get_event_loop()
        with self._app.create_action('play {}'.format(song)):
            await loop.run_in_executor(None, lambda: song.url)
            self._app.player.play_song(song)

    def play_all(self):
        songs = self.songs_table.model().songs
        self._app.player.playlist.clear()
        for song in songs:
            self._app.player.playlist.add(song)
        self._app.player.play_next()

    async def show_model(self, model):
        model_type = ModelType(model._meta.model_type)
        if model_type == ModelType.album:
            func = self.show_album
        elif model_type == ModelType.artist:
            func = self.show_artist
        elif model_type == ModelType.playlist:
            func = self.show_playlist
        else:
            def func(model): pass  # seems silly
        self._app.histories.append(model)
        with self._app.create_action('show {}'.format(str(model))):
            await func(model)

    def show_player_playlist(self, songs):
        self.show_songs(songs)
        self.songs_table.song_deleted.connect(
            lambda song: self._app.playlist.remove(song))

    async def show_playlist(self, playlist):
        self.table_overview.show()
        loop = asyncio.get_event_loop()
        songs = await loop.run_in_executor(None, lambda: playlist.songs)
        self._show_songs(songs)
        desc = '<h2>{}</h2>\n{}'.format(playlist.name, playlist.desc or '')
        self.table_overview.set_desc(desc)
        if playlist.cover:
            loop.create_task(self.show_cover(playlist.cover))

        def remove_song(song):
            model = self.songs_table.model()
            row = model.songs.index(song)
            # 如果有 f-string 该有多好！
            msg = 'remove {} from {}'.format(song, playlist)
            with self._app.create_action(msg) as action:
                rv = playlist.remove(song.identifier)
                if rv:
                    model.removeRow(row)
                else:
                    action.failed()

        self.songs_table.song_deleted.connect(lambda song: remove_song(song))

    async def show_artist(self, artist):
        self.table_overview.show()
        loop = asyncio.get_event_loop()
        future_songs = loop.run_in_executor(None, lambda: artist.songs)
        future_desc = loop.run_in_executor(None, lambda: artist.desc)
        await asyncio.wait([future_songs, future_desc])
        desc = future_desc.result()
        self.table_overview.set_desc(desc or '<h2>{}</h2>'.format(artist.name))
        self._show_songs(future_songs.result())
        if artist.cover:
            loop.create_task(self.show_cover(artist.cover))

    async def show_album(self, album):
        loop = asyncio.get_event_loop()
        future_songs = loop.run_in_executor(None, lambda: album.songs)
        future_desc = loop.run_in_executor(None, lambda: album.desc)
        await asyncio.wait([future_songs, future_desc])
        self.table_overview.set_desc(future_desc.result() or
                                     '<h2>{}</h2>'.format(album.name))
        songs = future_songs.result()
        self._show_songs(songs)
        if album.cover:
            loop.create_task(self.show_cover(album.cover))

    async def show_cover(self, cover):
        # FIXME: cover_hash may not work properly someday
        cover_uid = cover.split('/', -1)[-1]
        content = await self._app.img_ctl.get(cover, cover_uid)
        img = QImage()
        img.loadFromData(content)
        pixmap = QPixmap(img)
        if not pixmap.isNull():
            self.table_overview.set_cover(pixmap)
            self.update()

    def _show_songs(self, songs):
        try:
            self.songs_table.song_deleted.disconnect()
        except TypeError:  # no connections at all
            pass
        self.show()
        songs = songs or []
        logger.debug('Show songs in table, total: %d' % len(songs))
        source_name_map = {p.identifier: p.name for p in self._app.library.list()}
        self.songs_table.setModel(SongsTableModel(songs, source_name_map))
        self.songs_table.scrollToTop()

    def show_songs(self, songs):
        self._show_songs(songs)
        self.table_overview.hide()

    def search(self, text):
        if self.isVisible() and self.songs_table is not None:
            self.songs_table.filter_row(text)
