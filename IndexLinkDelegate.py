import re
from PySide6.QtWidgets import QStyledItemDelegate, QStyleOptionViewItem, QStyle, QApplication
from PySide6.QtGui import QColor, QFont, Qt, QCursor, QPalette, QPainter, QFontMetrics
from PySide6.QtCore import QEvent, QModelIndex, QRect

class IndexLinkDelegate(QStyledItemDelegate):
    """Styles IDn reference columns as underlined hyperlinks with cell-isolated token highlighting and hand cursors."""
    
    def paint(self, painter: QPainter, option, index: QModelIndex):
        if index.column() == 0:
            super().paint(painter, option, index)
            return

        custom_option = QStyleOptionViewItem(option)
        self.initStyleOption(custom_option, index)

        full_text = index.data(Qt.ItemDataRole.DisplayRole) or ""
        
        # 1. Synchronize the true underlined font metrics 
        base_font = custom_option.font
        hyperlink_font = QFont(base_font)
        hyperlink_font.setUnderline(True)
        font_metrics = QFontMetrics(hyperlink_font)
        custom_option.font = hyperlink_font

        # Isolate dark/light color themes
        main_win = custom_option.widget.window() if custom_option.widget else None
        is_dark = getattr(main_win, "is_dark_mode", False) if main_win else False
        link_color = QColor(102, 178, 255) if is_dark else QColor(0, 102, 204)
        custom_option.palette.setColor(QPalette.ColorRole.Text, link_color)

        # ----------------------------------------------------------------------
        # OBLITERATE FULL ROW HIGHLIGHT: STRIP NATIVE SELECTION BACKGROUND BRUSH
        # ----------------------------------------------------------------------
        # Stripping these flags forces the default engine to skip painting massive 
        # horizontal selection blocks entirely. We handle highlighting manually below!
        is_selected = bool(custom_option.state & QStyle.StateFlag.State_Selected)
        custom_option.state &= ~QStyle.StateFlag.State_Selected
        custom_option.state &= ~QStyle.StateFlag.State_HasFocus

        # Paint clean base cell parameters
        super().paint(painter, custom_option, index)

        if full_text and custom_option.widget:
            view_widget = custom_option.widget
            
            # Map tracking points starting precisely from the cell text origin sub-rectangle area
            style_engine = view_widget.style() if view_widget.style() else QApplication.style()
            text_rect = style_engine.subElementRect(QStyle.SubElement.SE_ItemViewItemText, custom_option, view_widget)
            
            cursor_pos_viewport = view_widget.viewport().mapFromGlobal(QCursor.pos())
            local_click_x = cursor_pos_viewport.x() - text_rect.x()
            
            tokens = [t.strip() for t in full_text.split() if t.strip()]
            current_offset_x = 0
            
            for token in tokens:
                token_width = font_metrics.horizontalAdvance(token)
                space_width = font_metrics.horizontalAdvance(" ")
                
                # Check if the mouse is currently interacting with this specific token string width bounds
                if (current_offset_x - 3) <= local_click_x <= (current_offset_x + token_width + 3):
                    # Highlight Rule: ONLY paint the highlight rectangle box if the cell row is actively selected!
                    if is_selected:
                        painter.save()
                        highlight_rect = QRect(
                            text_rect.x() + current_offset_x - 2,
                            custom_option.rect.y() + 2,
                            token_width + 4,
                            custom_option.rect.height() - 4
                        )
                        # Paint a crisp translucent amber highlight box isolated strictly over the selected token text area
                        painter.fillRect(highlight_rect, QColor(255, 200, 0, 80))
                        painter.restore()
                    break
                current_offset_x += token_width + space_width

    def editorEvent(self, event, model, option, index: QModelIndex) -> bool:
        """Processes mouse movements and clicks natively inside character bounds to toggle hand cursors and navigate tabs."""
        if not index.isValid() or index.column() != 1:
            return super().editorEvent(event, model, option, index)

        view = option.widget
        if not view:
            return super().editorEvent(event, model, option, index)

        full_text = index.data(Qt.ItemDataRole.DisplayRole) or ""
        if not full_text:
            return super().editorEvent(event, model, option, index)

        # Initialize synchronized font dimensions layout trackers
        base_font = option.font
        hyperlink_font = QFont(base_font)
        hyperlink_font.setUnderline(True)
        font_metrics = QFontMetrics(hyperlink_font)

        style_engine = view.style() if view.style() else QApplication.style()
        text_rect = style_engine.subElementRect(QStyle.SubElement.SE_ItemViewItemText, option, view)
        local_click_x = event.pos().x() - text_rect.x()

        tokens = [t.strip() for t in full_text.split() if t.strip()]
        current_offset_x = 0
        hovered_token = None

        for token in tokens:
            token_width = font_metrics.horizontalAdvance(token)
            if (current_offset_x - 3) <= local_click_x <= (current_offset_x + token_width + 3):
                hovered_token = token
                break
            current_offset_x += token_width + font_metrics.horizontalAdvance(" ")

        # 1. 100% RELIABLE HOVER HAND SYSTEM: Toggle cursor shapes based on text boundaries
        if event.type() == QEvent.Type.MouseMove:
            if hovered_token:
                if view.cursor().shape() != Qt.CursorShape.PointingHandCursor:
                    view.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
            else:
                if view.cursor().shape() != Qt.CursorShape.ArrowCursor:
                    view.unsetCursor()

        # 2. ZERO-DRIFT INTERACTION JUMP: Map token string straight to the data cache list
        elif event.type() == QEvent.Type.MouseButtonPress and event.button() == Qt.MouseButton.LeftButton:
            if hovered_token:
                try:
                    target_uid = int(hovered_token.strip("[](),.; "))
                    ROLE_UID_DATA = Qt.ItemDataRole.UserRole + 1
                    records_list = index.data(ROLE_UID_DATA)
                    
                    if records_list and isinstance(records_list, list):
                        for rec in records_list:
                            rec_id = rec.get("unique_id_number") or rec.get("id")
                            if rec and rec_id is not None and int(rec_id) == target_uid:
                                main_editor = view.window()
                                if main_editor and hasattr(main_editor, "go_to_index_location"):
                                    main_editor.go_to_index_location(
                                        str(rec.get("file_path")), 
                                        int(rec.get("line_number", 1)), 
                                        int(rec.get("column_offset", 0))
                                    )
                                break
                except ValueError:
                    pass
                
                # Force view redraw pass to let our custom token selection highlight box repaint instantly
                view.viewport().update()
                return True

        return super().editorEvent(event, model, option, index)
