#!/usr/bin/env python3
import sys
import os
import glob
import shutil
import termios
import tty
import argparse
import select
import copy

# 起動パスの絶対位置から、隣にある自作モジュールを確実に探索するためのパス注入ガード
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

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
            # 端末を生モードへ移行
            tty.setraw(fd)
            
            # バグ修正: 以前に混入していた、リストオブジェクトを破壊する
            # 不正なビット演算（new_settings &= ~termios.ISIG）を完全に削除・撤去。

            if hasattr(AppController, '_current_ev_action') and AppController._current_ev_action:
                act = AppController._current_ev_action
                AppController._current_ev_action = None
                if act == 'page_prev': return 'LEFT'
                if act == 'page_next': return 'RIGHT'

            r_fds = [fd]
            ev_dev = getattr(AppController, '_ev_device', None)
            if ev_dev:
                r_fds.append(ev_dev.fd)

            while True:
                readable, _, _ = select.select(r_fds, [], [])
                
                # バグ修正: 物理デバイスからの信号がある場合、標準入力側の誤読（空文字発生）を防ぐため
                # 物理キーボード由来の記述子を最優先で走査し、合致した瞬間に関数から離脱(return)させる
                if ev_dev and ev_dev.fd in readable:
                    ev_code = MultiplexInputController.consume_evdev(ev_dev)
                    act = AppController._config_loader.resolve_action(None, ev_code)
                    if act == 'page_prev': return 'LEFT'
                    if act == 'page_next': return 'RIGHT'
                    # 有効な割当ではない離鍵パケットなどの場合は、os.read へ落とさず即座に次の待機へ戻す
                    continue

                # 標準入力のみが読み込み可能な場合
                if fd in readable:
                    ch = os.read(fd, 1).decode('utf-8', errors='ignore')
                    
                    if ch == '\x1b':
                        orig_fl = termios.tcgetattr(fd)
                        # 安全にディープコピー
                        new_fl = copy.deepcopy(orig_fl)
                        new_fl[termios.VMIN] = 0
                        new_fl[termios.VTIME] = 1
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
            TerminalController.write("\033[32m[0-9a-z/ページ遷移キー] (ESC: キャンセル)\033[0m\n")
        else:
            TerminalController.write("[0-9a-z/ページ遷移キー]\n")
            
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
        
        validators = [SystemKeyValidator(), ReservedKeyValidator(KEYS)]
        AppController._config_loader = TSVConfigLoader(validators=validators)
        AppController._config_loader.load_and_validate()
        
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
                allowed_keys = ["0-9", "a-z", "←", "→"]
                for mapped_list in AppController._config_loader.mapping.values():
                    allowed_keys.extend(mapped_list)
                unique_keys = sorted(list(set(allowed_keys)), key=lambda s: len(s))
                self.error_msg = f"不正入力: 有効なキー（{', '.join(unique_keys)}）を押してください。"
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

