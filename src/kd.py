#!/usr/bin/env python3
import sys
import os
import shutil
import termios
import tty
import argparse

KEYS = "0123456789abcdefghijklmnopqrstuvwxyz"

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
            # 最初の1バイトを読み込み
            ch = os.read(fd, 1).decode('utf-8', errors='ignore')
            
            # エスケープシーケンスの解析
            if ch == '\x1b':
                # 後続の入力を非ブロッキングで確認
                orig_fl = termios.tcgetattr(fd)
                new_fl = termios.tcgetattr(fd)
                new_fl[6][termios.VMIN] = 0
                new_fl[6][termios.VTIME] = 1 # 0.1秒だけ待つ
                termios.tcsetattr(fd, termios.TCSANOW, new_fl)
                
                try:
                    seq2 = os.read(fd, 1).decode('utf-8', errors='ignore')
                    if seq2 == '[':
                        seq3 = os.read(fd, 1).decode('utf-8', errors='ignore')
                        if seq3 == 'D': return 'LEFT'
                        if seq3 == 'C': return 'RIGHT'
                        return 'UNKNOWN_SPECIAL' # F1, Del などの特殊キー
                    elif seq2 == '':
                        return 'ESC' # 後続がなければ純粋なESCキー
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


class LayoutEngine:
    """ページ毎・列毎の最適化数理ロジック（単一責任：レイアウト計算）"""
    def __init__(self, all_items, page, term_cols, term_lines, total_pages_guess=1):
        self.all_items = all_items
        self.page = page
        
        # UIパーツで消費する固定行数 (入力待機行1 + ページ行1)
        # ※初回計算時はページ行がある前提で安全にマージンを取る
        reserved_lines = 3 if total_pages_guess > 1 else 2
        self.max_rows = max(1, term_lines - reserved_lines)
        
        # 1ページあたりの最大アイテム数はキー上限(36)
        self.max_page_size = min(len(KEYS), term_cols) 
        
        # 暫定のページ切り出し
        # 縦並びグリッドを構築するため、まず列幅を動的に決定する
        # 最悪ケース（1列）からスタートし、何列入るかをシミュレーション
        self.cols = 1
        self.rows = min(self.max_rows, len(all_items))
        self.page_size = self.rows
        
        # 36文字制限と画面幅に合わせて列数を拡張
        for c in range(1, len(KEYS) + 1):
            test_rows = min(self.max_rows, (len(all_items) + c - 1) // c)
            test_size = min(len(KEYS), c * test_rows)
            
            # このページに入るアイテムを仮抽出
            start_idx = page * test_size
            page_items = all_items[start_idx:start_idx + test_size]
            if not page_items:
                break
                
            # 各列の最大幅を計算
            needed_width = 0
            for col_idx in range(c):
                col_items = page_items[col_idx * test_rows : (col_idx + 1) * test_rows]
                if col_items:
                    max_len = max(len(str(x)) for x in col_items)
                    needed_width += max_len + 5 # "0) " の3文字 + 余白2文字
                    
            if needed_width <= term_cols and test_size <= len(KEYS):
                self.cols = c
                self.rows = test_rows
                self.page_size = test_size
            else:
                break

        # 正確な総ページ数を算出
        self.total_pages = (len(all_items) + self.page_size - 1) // self.page_size if all_items else 1


class UIManager:
    """画面のレンダリング。上書き描画によるブレ防止（単一責任：表示表現）"""
    @staticmethod
    def render(items, page, layout, cancelable, error_msg=""):
        # カーソルを左上に戻し、画面全体をクリア
        TerminalController.write("\033[H\033[2J")
        
        # 1. 入力待機行＋プレースホルダー（1行目固定）
        TerminalController.write("? ")
        if error_msg:
            TerminalController.write(f"\033[31m{error_msg}\033[0m\n")
        elif cancelable:
            TerminalController.write("\033[32m[0-9a-z/矢印で選択] (ESC: キャンセル)\033[0m\n")
        else:
            TerminalController.write("[0-9a-z/矢印で選択]\n")
            
        # 2. ページ表示位置（2行目固定、1ページの時は非表示＝空行にしない）
        if layout.total_pages > 1:
            TerminalController.write(f"← {page + 1}/{layout.total_pages} →\n")
            
        # 3. アイテムグリッド描画（縦方向優先）
        start_idx = page * layout.page_size
        page_items = items[start_idx:start_idx + layout.page_size]
        
        # 各列の正確な最大長を再取得
        col_widths = []
        for c in range(layout.cols):
            col_items = page_items[c * layout.rows : (c + 1) * layout.rows]
            col_widths.append(max(len(str(x)) for x in col_items) if col_items else 0)
            
        # 行ごとに描画
        for r in range(layout.rows):
            row_str = ""
            for c in range(layout.cols):
                idx = c * layout.rows + r
                if idx < len(page_items):
                    key_char = KEYS[idx]
                    item_text = str(page_items[idx])
                    # 列幅に合わせてジャスティファイ
                    row_str += f"{key_char}) {item_text.ljust(col_widths[c])}  "
            TerminalController.write(row_str.rstrip() + "\n")


class AppController:
    """アプリケーションの状態管理と実行（単一責任：コントローラー）"""
    def __init__(self, items, cancelable):
        self.items = items
        self.cancelable = cancelable
        self.page = 0
        self.error_msg = ""

    def run(self):
        if not self.items:
            print("エラー: 選択肢がありません。", file=sys.stderr)
            sys.exit(1)

        # 画面を一度クリアして開始
        TerminalController.write("\033[H\033[2J")

        while True:
            cols, lines = TerminalController.get_size()
            
            # 初回ページ数予測を挟んで正確にレイアウトを計算
            layout = LayoutEngine(self.items, self.page, cols, lines)
            if layout.total_pages > 1:
                layout = LayoutEngine(self.items, self.page, cols, lines, total_pages_guess=layout.total_pages)
                
            # 安全ガード：ページ外に溢れたら0に戻す
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
                    TerminalController.write("\033[H\033[2J") # 画面を綺麗にして終了
                    sys.exit(130) # 中断ステータス
                else:
                    self.error_msg = "この操作はキャンセルできません。項目を選択してください。"
                continue
            elif key == '\x03': # Ctrl+C
                TerminalController.write("\033[H\033[2J")
                sys.exit(130)
            elif key in ('UNKNOWN_SPECIAL', ''):
                self.error_msg = "不正入力: 有効なキー（0-9, a-z, ←, →）を押してください。"
                continue
                
            # 選択処理
            start_idx = self.page * layout.page_size
            page_items = self.items[start_idx:start_idx + layout.page_size]
            
            if key in KEYS[:len(page_items)]:
                selected_idx = start_idx + KEYS.index(key)
                TerminalController.write("\033[H\033[2J") # 画面を綺麗にして終了
                print(self.items[selected_idx], flush=True) # stdoutへ出力
                sys.exit(0)
            else:
                # 視覚的に分かりやすいエラーメッセージに整形
                printable_key = key if key.isprintable() else f"0x{ord(key):02x}" if key else "None"
                self.error_msg = f"不正入力: [{printable_key}] 0-9, a-z, ←, → のみ有効です。"


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Keyboard-driven Item Selector")
    parser.add_argument('--cancelable', action='store_true', help='Allow cancellation with ESC key')
    parser.add_argument('items', nargs='*', help='Items to select from')
    args = parser.parse_args()

    AppController(args.items, args.cancelable).run()
