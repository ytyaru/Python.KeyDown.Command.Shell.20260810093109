#!/usr/bin/env python3
import sys
import os
import glob
import shutil
import termios
import tty
import argparse
import select
from evdev import InputDevice, ecodes

# 外部モジュールからロード
from config_loader import TSVConfigLoader, SystemKeyValidator, ReservedKeyValidator

KEYS = "0123456789abcdefghijklmnopqrstuvwxyz"

class DeviceManager:
    @staticmethod
    def find_keyboard():
        for path in glob.glob('/dev/input/event*'):
            try:
                dev = InputDevice(path)
                if ecodes.KEY_A in dev.capabilities().get(ecodes.EV_KEY, []):
                    return dev
            except Exception:
                continue
        return None

class TerminalContext:
    def __init__(self):
        self.fd = sys.stdin.fileno()

    @staticmethod
    def get_size():
        return shutil.get_terminal_size()

    def enter_raw_mode(self):
        old_settings = termios.tcgetattr(self.fd)
        tty.setraw(self.fd)
        new_settings = termios.tcgetattr(self.fd)
        new_settings[3] &= ~termios.ISIG
        termios.tcsetattr(self.fd, termios.TCSANOW, new_settings)
        return old_settings

    def restore(self, old_settings):
        termios.tcflush(sys.stdout.fileno(), termios.TCIOFLUSH)
        termios.tcflush(sys.stdin.fileno(), termios.TCIOFLUSH)
        termios.tcsetattr(self.fd, termios.TCSADRAIN, old_settings)

class LayoutEngine:
    def __init__(self, all_items, page, term_cols, term_lines, guess_pages=1):
        reserved = 3 if guess_pages > 1 else 2
        self.max_rows = max(1, term_lines - reserved)
        self.cols, self.rows = 1, min(self.max_rows, len(all_items))
        self.page_size = self.rows
        
        for c in range(1, len(KEYS) + 1):
            t_rows = min(self.max_rows, (len(all_items) + c - 1) // c)
            t_size = min(len(KEYS), c * t_rows)
            p_items = all_items[page * t_size : page * t_size + t_size]
            if not p_items:
                break
            width = sum(max(len(str(x)) for x in p_items[i*t_rows:(i+1)*t_rows])+5 for i in range(c) if p_items[i*t_rows:(i+1)*t_rows])
            if width <= term_cols and t_size <= len(KEYS):
                self.cols, self.rows, self.page_size = c, t_rows, t_size
            else:
                break
        self.total_pages = (len(all_items) + self.page_size - 1) // self.page_size if all_items else 1

class UIManager:
    @staticmethod
    def render(items, page, layout, cancelable, error_msg=""):
        # 画面を左上から上書きクリア
        sys.stderr.write("\033[H\033[2J?")
        if error_msg:
            sys.stderr.write(f" \033[31m{error_msg}\033[0m\r\n")
        elif cancelable:
            sys.stderr.write(" \033[32m[0-9a-z/ページ遷移キー] (ESC: キャンセル)\033[0m\r\n")
        else:
            sys.stderr.write(" [0-9a-z/ページ遷移キー]\r\n")
            
        if layout.total_pages > 1:
            sys.stderr.write(f"← {page + 1}/{layout.total_pages} →\r\n")
            
        p_items = items[page * layout.page_size : page * layout.page_size + layout.page_size]
        widths = [max(len(str(x)) for x in p_items[c*layout.rows:(c+1)*layout.rows]) if p_items[c*layout.rows:(c+1)*layout.rows] else 0 for c in range(layout.cols)]
        
        for r in range(layout.rows):
            row_str = ""
            for c in range(layout.cols):
                idx = c * layout.rows + r
                if idx < len(p_items):
                    row_str += f"{KEYS[idx]}) {str(p_items[idx]).ljust(widths[c])}  "
            sys.stderr.write(row_str.rstrip() + "\r\n")
        sys.stderr.flush()

class MultiplexInputController:
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
                for event in evdev_device.read():
                    if event.type == ecodes.EV_KEY and event.value == 1:
                        keycode_str = ecodes.KEY.get(event.code, None)
                        if keycode_str:
                            return None, keycode_str
        return None, None

class AppController:
    def __init__(self, items, cancelable):
        self.items = items
        self.cancelable = cancelable
        self.page = 0
        self.error_msg = ""
        
        validators = [
            SystemKeyValidator(),
            ReservedKeyValidator(KEYS)
        ]
        self.config = TSVConfigLoader(validators=validators)
        self.config.load_and_validate()
        
        self.evdev_device = DeviceManager.find_keyboard()
        self.terminal = TerminalContext()

    def run(self):
        if not self.items:
            print("エラー: 選択肢がありません。", file=sys.stderr)
            sys.exit(1)

        old_tty = self.terminal.enter_raw_mode()
        
        try:
            while True:
                cols, lines = self.terminal.get_size()
                layout = LayoutEngine(self.items, self.page, cols, lines)
                if layout.total_pages > 1:
                    layout = LayoutEngine(self.items, self.page, cols, lines, guess_pages=layout.total_pages)
                    
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
                    p_items = self.items[self.page * layout.page_size : self.page * layout.page_size + layout.page_size]
                    if tty_key in KEYS[:len(p_items)]:
                        sys.stderr.write("\033[H\033[2J")
                        sys.stderr.flush()
                        print(self.items[self.page * layout.page_size + KEYS.index(tty_key)], flush=True)
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
            self.terminal.restore(old_settings=old_tty)
            sys.stderr.write("\033[H\033[2J")
            sys.stderr.flush()

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--cancelable', action='store_true')
    parser.add_argument('items', nargs='*')
    args = parser.parse_args()
    AppController(args.items, args.cancelable).run()
