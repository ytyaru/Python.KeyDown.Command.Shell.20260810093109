#!/usr/bin/env python3
import sys
import os
import shutil
import termios
import tty
import select
import copy
import unicodedata
from evdev import ecodes
from layout_engine import KEYS
#from part.layout_engine import KEYS

def get_display_width(text):
    """全角文字・東アジアの曖昧な文字(Ambiguous)を2、半角文字を1として実際の表示幅を計算する"""
    width = 0
    for ch in str(text):
        status = unicodedata.east_asian_width(ch)
        if status in ('F', 'W', 'A'):
            width += 2
        else:
            width += 1
    return width

class MultiplexInputController:
    """物理キーのパケットが溜まっている場合に一気に吸い出す（単一責任）"""
    @staticmethod
    def consume_evdev(evdev_device):
        target_keycode = None
        try:
            while True:
                event = evdev_device.read_one()
                if event is None:
                    break
                if event.type == ecodes.EV_KEY and event.value == 1:
                    keycode_str = ecodes.KEY.get(event.code, None)
                    if keycode_str:
                        target_keycode = keycode_str
        except Exception:
            pass
        return target_keycode

class TerminalController:
    """端末制御とキー入力の厳密なハンドリング（単一責任：I/O）"""
    @staticmethod
    def get_size():
        return shutil.get_terminal_size()

    @staticmethod
    def read_key(app_instance):
        fd = sys.stdin.fileno()
        if not os.isatty(fd):
            with open('/dev/tty', 'r') as tty_fd:
                fd = tty_fd.fileno()
                return TerminalController._read(fd, app_instance)
        return TerminalController._read(fd, app_instance)

    @staticmethod
    def _read(fd, app_instance):
        old = termios.tcgetattr(fd)
        try:
            tty.setraw(fd)

            r_fds = [fd]
            ev_dev = getattr(app_instance, '_ev_device', None)
            if ev_dev:
                r_fds.append(ev_dev.fd)

            while True:
                readable, _, _ = select.select(r_fds, [], [])
                
                if ev_dev and ev_dev.fd in readable:
                    ev_code = MultiplexInputController.consume_evdev(ev_dev)
                    act = app_instance._config_loader.resolve_action(None, ev_code)
                    if act == 'page_prev': return 'LEFT'
                    if act == 'page_next': return 'RIGHT'
                    continue

                if fd in readable:
                    ch = os.read(fd, 1).decode('utf-8', errors='ignore')
                    
                    """
                    if ch == '\x1b':
                        orig_fl = termios.tcgetattr(fd)
                        new_fl = copy.deepcopy(orig_fl)
                        new_fl[termios.VMIN] = 0
                        new_fl[termios.VTIME] = 1
                        termios.tcsetattr(fd, termios.TCSANOW, new_fl)
                    """

                    if ch == '\x1b':
                        orig_fl = termios.tcgetattr(fd)
                        # バグ修正: copy.deepcopyを完全撤去。
                        # tcgetattrを再度呼び出して型が健全な新しいリストオブジェクトを直接取得する
                        new_fl = termios.tcgetattr(fd)
                        # リストの各設定項目（VMIN=4, VTIME=5）の値を直接上書き（型破壊が物理的に発生しません）
                        new_fl[6][termios.VMIN] = 0
                        new_fl[6][termios.VTIME] = 1
                        termios.tcsetattr(fd, termios.TCSANOW, new_fl)
                        
                        try:
                            seq2 = os.read(fd, 1).decode('utf-8', errors='ignore')
                            if seq2 == '[':
                                seq3 = os.read(fd, 1).decode('utf-8', errors='ignore')
                                if seq3 == 'D': return 'LEFT'
                                if seq3 == 'C': return 'RIGHT'
                                return 'UNKNOWN_SPECIAL'
                            elif seq2 == '':
                                return 'ESC'
                            return 'UNKNOWN_SPECIAL'
                        except Exception:
                            return 'UNKNOWN_SPECIAL'
                        finally:
                            termios.tcsetattr(fd, termios.TCSANOW, orig_fl)
                    return ch
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, old)

    @staticmethod
    def write(text):
        sys.stderr.write(text)
        sys.stderr.flush()

class UIManager:
    """画面のレンダリング。上書き描画によるブレ防止（単一責任：表示表現）"""
    @staticmethod
    def render(items, page, layout, cancelable, error_msg=""):
        TerminalController.write("\033[H\033[2J")
        TerminalController.write("? ")
        if error_msg:
            TerminalController.write(f"\033[31m{error_msg}\033[0m\n")
        elif cancelable:
            TerminalController.write("\033[32m[0-9a-z/ページ遷移キー] (ESC: キャンセル)\033[0m\n")
        else:
            TerminalController.write("[0-9a-z/ページ遷移キー]\n")
            
        if layout.total_pages > 1:
            TerminalController.write(f"← {page + 1}/{layout.total_pages} →\n")
            
        from layout_engine import LayoutEngine
        start_idx = 0
        for p in range(page):
            cols, lines = TerminalController.get_size()
            tmp_layout = LayoutEngine(items, p, cols, lines)
            if tmp_layout.total_pages > 1:
                tmp_layout = LayoutEngine(items, p, cols, lines, total_pages_guess=tmp_layout.total_pages)
            start_idx += tmp_layout.page_size
            
        page_items = items[start_idx:start_idx + layout.page_size]
        
        col_widths = []
        for c in range(layout.cols):
            col_items = page_items[c * layout.rows : (c + 1) * layout.rows]
            col_widths.append(max(get_display_width(x) for x in col_items) if col_items else 0)
            
        for r in range(layout.rows):
            row_str = ""
            for c in range(layout.cols):
                idx = c * layout.rows + r
                if idx < len(page_items):
                    key_char = KEYS[idx]
                    item_text = str(page_items[idx])
                    pad_len = col_widths[c] - get_display_width(item_text)
                    row_str += f"{key_char}) {item_text}{' ' * pad_len}  "
            TerminalController.write(row_str.rstrip() + "\n")

