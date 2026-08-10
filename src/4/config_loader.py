#!/usr/bin/env python3
import sys
import os
from evdev import ecodes

class TSVConfigLoader:
    """keymap.tsv の構文および実在するevdev定数名のバリデーションを担当"""
    VALID_ACTIONS = {'page_prev', 'page_next'}

    def __init__(self):
        # デフォルトのマッピング設定
        self.mapping = {
            'page_prev': ['LEFT', 'KEY_MUHENKAN'],
            'page_next': ['RIGHT', 'KEY_HENKAN']
        }
        # evdevに登録されている、システム上有効なすべての定数名の集合
        self.valid_evdev_keys = set(ecodes.KEY.values())

    def _print_help_and_exit(self, error_message):
        """エラーメッセージと外部ヘルプファイルを出力してステータス1で終了する"""
        print(f"【エラー】: {error_message}\n", file=sys.stderr)
        
        # 外部の仕様通知テキストファイルのロードを試みる
        help_path = './keymap_help.txt'
        if os.path.exists(help_path):
            with open(help_path, 'r', encoding='utf-8') as h_f:
                print(h_f.read(), file=sys.stderr)
        else:
            print("警告: ヘルプファイル(keymap_help.txt)が見つかりません。", file=sys.stderr)
            
        sys.exit(1)

    def load_and_validate(self):
        search_paths = [
            './keymap.tsv',
            os.path.expanduser('~/.config/kd/keymap.tsv'),
            os.path.expanduser('~/.local/kd/keymap.tsv')
        ]
        target_path = next((p for p in search_paths if os.path.exists(p)), None)
        if not target_path:
            return  # ファイルがない場合はデフォルトマッピングで動作

        line_no = 0
        try:
            with open(target_path, 'r', encoding='utf-8') as f:
                for line in f:
                    line_no += 1
                    line_raw = line.strip()
                    if not line_raw or line_raw.startswith('#'):
                        continue

                    # タブ区切りチェック
                    parts = line_raw.split('\t')
                    if len(parts) != 2:
                        self._print_help_and_exit(
                            f"設定構文不正 ({target_path}:{line_no}): 行は『用途ID[TAB]定数名』の2要素で構成されている必要があります。"
                        )

                    action, key_name = parts[0].strip(), parts[1].strip()

                    # 用途ID（アクション）の妥当性チェック
                    if action not in self.VALID_ACTIONS:
                        self._print_help_and_exit(
                            f"未知の用途ID ({target_path}:{line_no}): '{action}' は無効です。"
                        )

                    # evdevに実在する定数名かどうかのチェック
                    if key_name not in self.valid_evdev_keys and key_name not in ('LEFT', 'RIGHT'):
                        self._print_help_and_exit(
                            f"不正なキー定数名 ({target_path}:{line_no}): '{key_name}' はシステムに存在しません。"
                        )

                    # バリデーション通過時、ユーザー定義がある場合はデフォルトを消去して上書き
                    if len(self.mapping[action]) == 2:
                        self.mapping[action] = []
                    self.mapping[action].append(key_name)

        except Exception as e:
            print(f"エラー: 設定ファイルの読み込み中に重大な問題が発生しました: {e}", file=sys.stderr)
            sys.exit(1)

    def resolve_action(self, tty_key, evdev_keycode):
        """TTYの入力、またはevdevの物理キー名からアクションを判定"""
        for action, codes in self.mapping.items():
            if tty_key in codes or evdev_keycode in codes:
                return action
        return None

