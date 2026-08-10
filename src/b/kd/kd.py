#!/usr/bin/env python3
import sys
import os
import glob
import argparse
from evdev import InputDevice, ecodes

# 起動パスの絶対位置から、隠蔽された part ディレクトリを最優先探索パスに注入
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PART_DIR = os.path.join(BASE_DIR, 'part')
if PART_DIR not in sys.path:
    sys.path.insert(0, PART_DIR)

# 外部分割モジュール群のインポート
from layout_engine import LayoutEngine, KEYS
from config_loader import TSVConfigLoader, SystemKeyValidator, ReservedKeyValidator
from terminal_io import TerminalController, UIManager
#from part.layout_engine import LayoutEngine, KEYS
#from part.config_loader import TSVConfigLoader, SystemKeyValidator, ReservedKeyValidator
#from part.terminal_io import TerminalController, UIManager
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

class AppController:
    """アプリケーションの状態管理と実行（単一責任：コントローラー）"""
    def __init__(self, items, cancelable):
        self.items = items
        self.cancelable = cancelable
        self.page = 0
        self.error_msg = ""
        
        validators = [SystemKeyValidator(), ReservedKeyValidator(KEYS)]
        self._config_loader = TSVConfigLoader(validators=validators)
        self._config_loader.load_and_validate()
        
        self._ev_device = DeviceManager.find_keyboard()

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
            
            # 引数にself(状態インスタンス)を渡して多重化I/Oを安全に駆動
            key = TerminalController.read_key(self)
            
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
                for mapped_list in self._config_loader.mapping.values():
                    allowed_keys.extend(mapped_list)
                unique_keys = sorted(list(set(allowed_keys)), key=lambda s: len(s))
                self.error_msg = f"不正入力: 有効なキー（{', '.join(unique_keys)}）を押してください。"
                continue
                
            start_idx = 0
            for p in range(self.page):
                tmp_layout = LayoutEngine(self.items, p, cols, lines)
                if tmp_layout.total_pages > 1:
                    tmp_layout = LayoutEngine(self.items, p, cols, lines, total_pages_guess=tmp_layout.total_pages)
                start_idx += tmp_layout.page_size
                
            page_items = self.items[start_idx:start_idx + layout.page_size]
            
            if key in KEYS[:len(page_items)]:
                selected_idx = start_idx + KEYS.index(key)
                TerminalController.write("\033[H\033[2J")
                print(self.items[selected_idx], flush=True)
                sys.exit(0)
            else:
                printable_key = key if key.isprintable() else f"0x{ord(key):02x}" if key else "None"
                self.error_msg = f"不正入力: [{printable_key}] 0-9, a-z または 登録された遷移キーのみ有効です。"

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Keyboard-driven Item Selector")
    parser.add_argument('--cancelable', action='store_true', help='Allow cancellation with ESC key')
    parser.add_argument('items', nargs='*')
    args = parser.parse_args()

    AppController(args.items, args.cancelable).run()

