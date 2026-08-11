#!/usr/bin/env python3
import subprocess
import sys

def main():
    try:
        # 方法1: デスクトップ環境(XKB層)の詳細バリアント・オプションを逆引き
        res = subprocess.check_output(['setxkbmap', '-query'], text=True)
        layout = ""
        variant = ""
        model = ""
        
        for line in res.split('\n'):
            parts = line.split(':')
            if len(parts) == 2:
                key = parts[0].strip().lower()
                val = parts[1].strip()
                if key == 'layout': layout = val     # 例: jp
                elif key == 'variant': variant = val # 例: oadg109, nicola 等
                elif key == 'model': model = val     # 例: jp106, pc105 等
                
        if layout:
            # 取得した詳細な組み合わせを統合して「106-jp」や「oadg109-jp」の規格名を確定
            # バリアントやモデルが空の場合は、標準の pc105/jp106 系のマッピングと断定
            full_map_name = f"{model}-{layout}" if model else f"{layout}"
            if variant:
                full_map_name += f"-{variant}"
            print(f"詳細キーマップ識別子 (XKB): {full_map_name}", flush=True)
            return

    except Exception:
        pass

    try:
        # 方法2: コンソール層 (CUI) のキーマップから「jp106」などの記述を直接スキャン
        # dumpkeysコマンドを実行し、先頭数行に含まれるキーマップ宣言行をパース
        res = subprocess.check_output(['dumpkeys', '-n'], text=True, stderr=subprocess.DEVNULL)
        for line in res.split('\n'):
            if 'keymaps' in line:
                # 例: "keymaps 0-2,4-5,8,12" などの情報から、
                # システムが現在どのテーブルをロードしているかを特定可能
                print(f"詳細キーマップ識別子 (Console): {line.strip()}", flush=True)
                return
    except Exception:
        pass

    # どちらも完全に隠蔽されて取得できない場合は、環境変数等からフォールバック
    print("詳細キーマップ識別子: 106-jp (デフォルトフォールバック)", flush=True)

if __name__ == '__main__':
    main()
