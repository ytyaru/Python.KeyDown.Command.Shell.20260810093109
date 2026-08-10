#!/usr/bin/env python3
import sys
import os
import shutil
import termios
import tty
import argparse
import select
import glob
from evdev import InputDevice, ecodes

# 外部自作モジュール群のインポート
from layout_engine import LayoutEngine, KEYS
from config_loader import TSVConfigLoader, SystemKeyValidator, ReservedKeyValidator

class DeviceManager:
    """有効な物理キーボードデバイスを探索する（単一責任）"""
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
            except Exception:
                continue
        return None

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

# --- 1/5: TerminalController ---
class TerminalController:
    """端末制御とキー入力の厳密なハンドリング（単一責任：I/O）"""
    @staticmethod
    def get_size():
        return shutil.get_terminal_size()

    @staticmethod
    def read_key():
        """特殊キーの誤判定を防ぐ厳密なキー読み取り"""
        fd = sys.stdin.fileno()
        if not os.isatty(fd):
            with open('/dev/tty', 'r') as tty_fd:
                fd = tty_fd.fileno()
                return TerminalController._read(fd)
        return TerminalController._read(fd)

    @staticmethod
    def _read(fd):
        old = termios.tcgetattr(fd)
        try:
            tty.setraw(fd)
            # 外部注入されたグローバル変数から、すでに多重検知された物理キーがあればインターセプトする
            if hasattr(AppController, '_current_ev_action') and AppController._current_ev_action:
                act = AppController._current_ev_action
                AppController._current_ev_action = None
                if act == 'page_prev': return 'LEFT'
                if act == 'page_next': return 'RIGHT'

            # 物理キーボード(evdev)のファイル記述子も同時にselectでブロッキング監視するよう多重化拡張
            # これにより、文字入力または無変換・変換のいずれかが届くまでCPU消費ゼロで完全停止します
            r_fds = [fd]
            ev_dev = getattr(AppController, '_ev_device', None)
            if ev_dev:
                r_fds.append(ev_dev.fd)

            readable, _, _ = select.select(r_fds, [], [])
            
            for ready_fd in readable:
                if ev_dev and ready_fd == ev_dev.fd:
                    # 物理キーが押された場合、パケットを全消費してマッピングを解決
                    ev_code = MultiplexInputController.consume_evdev(ev_dev)
                    act = AppController._config_loader.resolve_action(None, ev_code)
                    if act == 'page_prev': return 'LEFT'
                    if act == 'page_next': return 'RIGHT'
                    return 'UNKNOWN_SPECIAL'

            # 通常の標準入力処理
            ch = os.read(fd, 1).decode('utf-8', errors='ignore')
            
            if ch == '\x1b':
                orig_fl = termios.tcgetattr(fd)
                new_fl = termios.tcgetattr(fd)
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
                finally:
                    termios.tcsetattr(fd, termios.TCSANOW, orig_fl)
            return ch
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, old)

    @staticmethod
    def write(text):
        sys.stderr.write(text)
        sys.stderr.flush()

# --- 3/5: UIManager ---
class UIManager:
    """画面のレンダリング。上書き描画によるブレ防止（単一責任：表示表現）"""
    @staticmethod
    def render(items, page, layout, cancelable, error_msg=""):
        TerminalController.write("\033[H\033[2J")
        TerminalController.write("? ")
        if error_msg:
            TerminalController.write(f"\033[31m{error_msg}\033[0m\n")
        elif cancelable:
            TerminalController.write("\033[32m[0-9a-z/矢印で選択] (ESC: キャンセル)\033[0m\n")
        else:
            TerminalController.write("[0-9a-z/矢印で選択]\n")
            
        if layout.total_pages > 1:
            TerminalController.write(f"← {page + 1}/{layout.total_pages} →\n")
            
        start_idx = page * layout.page_size
        page_items = items[start_idx:start_idx + layout.page_size]
        
        col_widths = []
        for c in range(layout.cols):
            col_items = page_items[c * layout.rows : (c + 1) * layout.rows]
            col_widths.append(max(len(str(x)) for x in col_items) if col_items else 0)
            
        for r in range(layout.rows):
            row_str = ""
            for c in range(layout.cols):
                idx = c * layout.rows + r
                if idx < len(page_items):
                    key_char = KEYS[idx]
                    item_text = str(page_items[idx])
                    row_str += f"{key_char}) {item_text.ljust(col_widths[c])}  "
            TerminalController.write(row_str.rstrip() + "\n")

# --- 4/5: AppController ---
class AppController:
    """アプリケーションの状態管理と実行（単一責任：コントローラー）"""
    _ev_device = None
    _current_ev_action = None
    _config_loader = None

    def __init__(self, items, cancelable):
        self.items = items
        self.cancelable = cancelable
        self.page = 0
        self.error_msg = ""
        
        # 外付けTSVロードと予約キー制限バリデーターの動的注入
        validators = [SystemKeyValidator(), ReservedKeyValidator(KEYS)]
        AppController._config_loader = TSVConfigLoader(validators=validators)
        AppController._config_loader.load_and_validate()
        
        # 物理キーボードデバイスの自動検出とコンテキスト登録
        AppController._ev_device = DeviceManager.find_keyboard()

    def run(self):
        if not self.items:
            print("エラー: 選択肢がありません。", file=sys.stderr)
            sys.exit(1)

        TerminalController.write("\033[H\033[2J")

        while True:
            cols, lines = TerminalController.get_size()
            
            layout = LayoutEngine(self.items, self.page, cols, lines)
            if layout.total_pages > 1:
                layout = LayoutEngine(self.items, self.page, cols, lines, total_pages_guess=layout.total_pages)
                
            if self.page >= layout.total_pages:
                self.page = 0
                
            UIManager.render(self.items, self.page, layout, self.cancelable, self.error_msg)
            self.error_msg = ""
            
            key = TerminalController.read_key()
            
            if key == 'LEFT':
                if layout.total_pages > 1:
                    self.page = (self.page - 1) % layout.total_pages
                continue
            elif key == 'RIGHT':
                if layout.total_pages > 1:
                    self.page = (self.page + 1) % layout.total_pages
                continue
            elif key == 'ESC':
                if self.cancelable:
                    TerminalController.write("\033[H\033[2J")
                    sys.exit(130)
                else:
                    self.error_msg = "この操作はキャンセルできません。項目を選択してください。"
                continue
            elif key == '\x03':
                TerminalController.write("\033[H\033[2J")
                sys.exit(130)
            elif key in ('UNKNOWN_SPECIAL', ''):
                self.error_msg = "不正入力: 有効なキー（0-9, a-z, 変換, 無変換）を押してください。"
                continue
                
            start_idx = self.page * layout.page_size
            page_items = self.items[start_idx:start_idx + layout.page_size]
            
            if key in KEYS[:len(page_items)]:
                selected_idx = start_idx + KEYS.index(key)
                TerminalController.write("\033[H\033[2J")
                print(self.items[selected_idx], flush=True)
                sys.exit(0)
            else:
                printable_key = key if key.isprintable() else f"0x{ord(key):02x}" if key else "None"
                self.error_msg = f"不正入力: [{printable_key}] 0-9, a-z または 登録された遷移キーのみ有効です。"

# --- 5/5: Main Entry ---
if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Keyboard-driven Item Selector")
    parser.add_argument('--cancelable', action='store_true', help='Allow cancellation with ESC key')
    parser.add_argument('items', nargs='*')
    args = parser.parse_args()

    AppController(args.items, args.cancelable).run()
