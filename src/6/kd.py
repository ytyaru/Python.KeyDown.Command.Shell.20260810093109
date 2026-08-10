#!/usr/bin/env python3
import sys
import os
import glob
import termios
import tty
import argparse
import select
import shutil
from evdev import InputDevice, ecodes

# 外部自作モジュール群のインポート
from config_loader import TSVConfigLoader, SystemKeyValidator, ReservedKeyValidator
from layout_engine import LayoutEngine, get_display_width, KEYS

class DeviceManager:
    """物理キーボードの自動探索を担当（単一責任）"""
    @staticmethod
    def find_keyboard():
        for path in glob.glob('/dev/input/event*'):
            try:
                dev = InputDevice(path)
                caps = dev.capabilities()
                key_caps = caps.get(ecodes.EV_KEY, [])
                if (ecodes.KEY_A in key_caps and 
                    ecodes.KEY_Z in key_caps and 
                    ecodes.KEY_SPACE in key_caps):
                    return dev
            except (OSError, AttributeError, TypeError, ValueError, KeyError):
                continue
            except Exception:
                continue
        return None

class TerminalContext:
    """端末状態の生モード制御のみを担当（単一責任）"""
    def __init__(self):
        self.fd = sys.stdin.fileno()

    def enter_raw_mode(self):
        old_settings = termios.tcgetattr(self.fd)
        tty.setraw(self.fd)
        new_settings = termios.tcgetattr(self.fd)
        # 型エラー修正: リストの3番目のインデックス(LFLAG)に対してビット演算を適用
        new_settings[3] &= ~termios.ISIG
        termios.tcsetattr(self.fd, termios.TCSANOW, new_settings)
        return old_settings

    def restore(self, old_settings):
        try:
            termios.tcflush(self.fd, termios.TCIFLUSH)
        except Exception:
            pass
        termios.tcsetattr(self.fd, termios.TCSADRAIN, old_settings)

class UIManager:
    """画面の上書きレンダリングのみを担当（単一責任）"""
    @staticmethod
    def render(items, page, layout, cancelable, error_msg=""):
        sys.stderr.write("\033[H\033[2J?")
        if error_msg:
            sys.stderr.write(f" \033[31m{error_msg}\033[0m\r\n")
        elif cancelable:
            sys.stderr.write(" \033[32m[0-9a-z/ページ遷移キー] (ESC: キャンセル)\033[0m\r\n")
        else:
            sys.stderr.write(" [0-9a-z/ページ遷移キー]\r\n")
            
        if layout.total_pages > 1:
            sys.stderr.write(f"← {page + 1}/{layout.total_pages} →\r\n")
            
        start_idx, (cols, rows, size) = layout.get_page_info(page)
        p_items = items[start_idx : start_idx + size]
        
        widths = []
        for c in range(cols):
            col_items = p_items[c * rows : (c + 1) * rows]
            widths.append(max(get_display_width(x) for x in col_items) if col_items else 0)
        
        for r in range(rows):
            row_str = ""
            for c in range(cols):
                idx = c * rows + r
                if idx < len(p_items):
                    item_text = str(p_items[idx])
                    pad_len = widths[c] - get_display_width(item_text)
                    row_str += f"{KEYS[idx]}) {item_text}{' ' * pad_len}  "
            sys.stderr.write(row_str.rstrip() + "\r\n")
        sys.stderr.flush()

class MultiplexInputController:
    """TTY標準入力とevdevデバイスの多重監視・キャプチャのみを担当（単一責任）"""
    @staticmethod
    def read_input(evdev_device):
        tty_fd = sys.stdin.fileno()
        r_fds = [tty_fd]
        if evdev_device:
            r_fds.append(evdev_device.fd)
            
        readable, _, _ = select.select(r_fds, [], [])
        
        for fd in readable:
            if fd == tty_fd:
                ch = sys.stdin.read(1)
                if ch == '\x1b':
                    r, _, _ = select.select([tty_fd], [], [], 0.05)
                    if r:
                        ch2 = sys.stdin.read(1)
                        if ch2 == '[':
                            ch3 = sys.stdin.read(1)
                            if ch3 == 'D': return 'LEFT', None
                            if ch3 == 'C': return 'RIGHT', None
                        return 'UNKNOWN_SPECIAL', None
                    return 'ESC', None
                return ch, None
                
            elif evdev_device and fd == evdev_device.fd:
                try:
                    for event in evdev_device.read():
                        if event.type == ecodes.EV_KEY and event.value == 1:
                            keycode_str = ecodes.KEY.get(event.code, None)
                            if keycode_str:
                                return None, keycode_str
                except Exception:
                    pass
        return None, None

class AppController:
    """全体のオーケストレーションと状態遷移を担当（単一責任）"""
    def __init__(self, items, cancelable):
        self.items = items
        self.cancelable = cancelable
        self.page = 0
        self.error_msg = ""
        
        validators = [SystemKeyValidator(), ReservedKeyValidator(KEYS)]
        self.config = TSVConfigLoader(validators=validators)
        self.config.load_and_validate()
        
        self.evdev_device = DeviceManager.find_keyboard()
        self.terminal = TerminalContext()

    def run(self):
        if not self.items:
            print("エラー: 選択肢がありません。", file=sys.stderr)
            sys.exit(1)

        old_tty = None
        try:
            old_tty = self.terminal.enter_raw_mode()
            while True:
                # 修正: 不要な割当行を削除
                term_w, term_h = shutil.get_terminal_size()
                layout = LayoutEngine(self.items, term_w, term_h)
                
                if self.page >= layout.total_pages:
                    self.page = 0
                    
                UIManager.render(self.items, self.page, layout, self.cancelable, self.error_msg)
                self.error_msg = ""
                
                tty_key, ev_code = MultiplexInputController.read_input(self.evdev_device)
                action = self.config.resolve_action(tty_key, ev_code)
                
                if action == 'page_prev' or tty_key == 'LEFT':
                    if layout.total_pages > 1:
                        self.page = (self.page - 1) % layout.total_pages
                    continue
                elif action == 'page_next' or tty_key == 'RIGHT':
                    if layout.total_pages > 1:
                        self.page = (self.page + 1) % layout.total_pages
                    continue
                elif tty_key == 'ESC':
                    if self.cancelable:
                        sys.exit(130)
                    self.error_msg = "この操作はキャンセルできません。項目を選択してください。"
                    continue
                elif tty_key == '\x03':
                    sys.exit(130)
                elif tty_key == 'UNKNOWN_SPECIAL':
                    self.error_msg = "不正入力: 有効なキーを押してください。"
                    continue
                    
                if tty_key:
                    start_idx, (_, _, size) = layout.get_page_info(self.page)
                    p_items = self.items[start_idx : start_idx + size]
                    
                    if tty_key in KEYS[:len(p_items)]:
                        sys.stderr.write("\033[H\033[2J")
                        sys.stderr.flush()
                        
                        final_selected_idx = start_idx + KEYS.index(tty_key)
                        print(self.items[final_selected_idx], flush=True)
                        sys.exit(0)
                    else:
                        p_key = tty_key if tty_key.isprintable() else f"0x{ord(tty_key):02x}"
                        self.error_msg = f"不正入力: [{p_key}] 0-9, a-z または 登録された遷移キーのみ有効です。"
        finally:
            if self.evdev_device:
                try:
                    self.evdev_device.close()
                except Exception:
                    pass
            if old_tty is not None:
                self.terminal.restore(old_settings=old_tty)
            sys.stderr.write("\033[H\033[2J")
            sys.stderr.flush()

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--cancelable', action='store_true')
    parser.add_argument('items', nargs='*')
    args = parser.parse_args()
    AppController(args.items, args.cancelable).run()
