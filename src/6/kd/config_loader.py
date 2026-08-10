#!/usr/bin/env python3
import sys
import os
from evdev import ecodes

class SystemKeyValidator:
    """evdevシステム上に実在するキー名であるかを検証する（単一責任）"""
    def __init__(self):
        self.valid_names = set()
        for v in ecodes.KEY.values():
            if isinstance(v, list):
                self.valid_names.update(v)
            else:
                self.valid_names.add(v)
        self.valid_names.update(['LEFT', 'RIGHT'])

    def validate(self, key_name):
        if key_name not in self.valid_names:
            return f"不正なキー定数名 '{key_name}' です。システムに存在しません。"
        return None

class ReservedKeyValidator:
    """kdの選択キー[0-9a-z]と衝突する予約キーではないかを検証する（単一責任）"""
    def __init__(self, reserved_chars):
        self.forbidden_keys = set()
        for char in reserved_chars:
            self.forbidden_keys.add(f"KEY_{char.upper()}")

    def validate(self, key_name):
        if key_name in self.forbidden_keys:
            return f"予約キー制限エラー: '{key_name}' はアイテム選択用に予約されているため、遷移キーに指定できません。"
        return None

class TSVConfigLoader:
    """TSVの純粋なパースとバリデータへの仲介のみを担当（単一責任）"""
    VALID_ACTIONS = {'page_prev', 'page_next'}

    def __init__(self, validators=None):
        self.mapping = {
            'page_prev': ['LEFT', 'KEY_MUHENKAN'],
            'page_next': ['RIGHT', 'KEY_HENKAN']
        }
        self.validators = validators if validators is not None else []

    def _print_help_and_exit(self, error_message):
        print(f"【エラー】: {error_message}\n", file=sys.stderr)
        help_path = './keymap_help.txt'
        if os.path.exists(help_path):
            with open(help_path, 'r', encoding='utf-8') as h_f:
                print(h_f.read(), file=sys.stderr)
        sys.exit(1)

    def load_and_validate(self):
        search_paths = [
            './keymap.tsv',
            os.path.expanduser('~/.config/kd/keymap.tsv'),
            os.path.expanduser('~/.local/kd/keymap.tsv')
        ]
        target_path = next((p for p in search_paths if os.path.exists(p)), None)
        if not target_path:
            return

        line_no = 0
        try:
            with open(target_path, 'r', encoding='utf-8') as f:
                for line in f:
                    line_no += 1
                    line_raw = line.strip()
                    if not line_raw or line_raw.startswith('#'):
                        continue

                    parts = line_raw.split('\t')
                    if len(parts) != 2:
                        self._print_help_and_exit(f"設定構文不正 ({target_path}:{line_no}): 『用途ID[TAB]定数名』の2要素が必要です。")

                    # バグ修正: 構文崩壊を完全に修正し、インデックスを指定
                    action, key_name = parts[0].strip(), parts[1].strip()

                    if action not in self.VALID_ACTIONS:
                        self._print_help_and_exit(f"未知の用途ID ({target_path}:{line_no}): '{action}' は無効です。")

                    for validator in self.validators:
                        err = validator.validate(key_name)
                        if err:
                            self._print_help_and_exit(f"バリデーション失敗 ({target_path}:{line_no}): {err}")

                    if len(self.mapping[action]) == 2:
                        self.mapping[action] = []
                    self.mapping[action].append(key_name)

        except SystemExit:
            sys.exit(1)
        except Exception as e:
            print(f"エラー: 設定ファイルの読み込み中に重大な問題が発生しました: {e}", file=sys.stderr)
            sys.exit(1)

    def resolve_action(self, tty_key, evdev_keycode):
        for action, codes in self.mapping.items():
            if tty_key in codes or evdev_keycode in codes:
                return action
        return None
