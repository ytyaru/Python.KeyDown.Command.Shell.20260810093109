#!/usr/bin/env python3
import sys
import os
from evdev import ecodes

class TSVConfigLoader:
    """メタデータ付き独自混在設定ファイルのパースと、OS状態との自動選別を担当（単一責任）"""
    def __init__(self, current_dev_id, current_layout):
        self.current_dev_id = current_dev_id  # 例: "USB_04f2_1234"
        self.current_layout = current_layout  # 例: "jp" (106-jp)
        
        # デフォルトのフォールバック設定
        self.meta = {
            'DEVICE': 'UNKNOWN',
            'KEYMAP': 'UNKNOWN',
            'PAGE_PREV': 'KEY_MUHENKAN',
            'PAGE_NEXT': 'KEY_HENKAN'
        }
        self.selection_keys = [] # 1ストローク選択用リスト（文字またはKEY_名の混在をそのまま保持）

    def load_strategy_file(self, strategy_name):
        """例: '24-key.tsv' を指定し、デバイスとキーマップに合致するファイルを自動探索・ロード"""
        base_dir = os.path.dirname(os.path.abspath(__file__))
        parent_dir = os.path.dirname(base_dir) # kd/ ディレクトリ
        
        # あなたが提示した3次元構造 (key/デバイス/キーマップ/戦略.tsv) の探索パスをビルド
        target_path = os.path.join(
            parent_dir, 'key', self.current_dev_id, self.current_layout, strategy_name
        )
        
        # もし固有の3次元ディレクトリがなければ、直下のデフォルトファイルを探索
        if not os.path.exists(target_path):
            target_path = os.path.join(parent_dir, strategy_name)
            if not os.path.exists(target_path):
                print(f"【エラー】設定ファイル {strategy_name} が見つかりません。", file=sys.stderr)
                sys.exit(1)

        line_no = 0
        with open(target_path, 'r', encoding='utf-8') as f:
            for line in f:
                line_no += 1
                # 修正の事実: コメント記号を # から // へ完全移行
                line_raw = line.split('//')[0].strip()
                if not line_raw:
                    continue

                # 冒頭のメタデータ行 (KEY=VALUE) の解析
                if '=' in line_raw and len(self.selection_keys) == 0:
                    k, v = line_raw.split('=', 1)
                    self.meta[k.strip()] = v.strip()
                    continue

                # ここに到達した行は、すべて純粋な「1ストローク選択キー」
                # 文字（f, ;, + 等）であっても、KEY_MUHENKAN 等であっても、そのまま順番通りリストに格納
                self.selection_keys.append(line_raw)

        # OSの現在のハードウェア情報と、読み込んだ設定ファイルのメタデータに齟齬がないかを厳格に防衛検証
        # (ただし、デフォルトファイル読み込み時はスキップ)
        if self.meta['DEVICE'] != 'UNKNOWN' and self.meta['DEVICE'] != self.current_dev_id:
            print(f"【警告】デバイス不一致: 現在の機器は {self.current_dev_id} ですが、設定は {self.meta['DEVICE']} です。", file=sys.stderr)

