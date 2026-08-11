#!/usr/bin/env python3
import glob
import sys
from evdev import InputDevice, ecodes

def main():
    print("=== Linux入力デバイス 徹底解析・追跡調査開始 ===", flush=True)
    
    # 1. そもそもシステムからファイルが取得できているか
    event_paths = sorted(glob.glob('/dev/input/event*'))
    print(f"[調査1] /dev/input/event* の検出数: {len(event_paths)} 個")
    if not event_paths:
        print("❌ 失敗: /dev/input/event* が1つも見つかりません。権限や環境を確認してください。", file=sys.stderr)
        sys.exit(1)
        
    for path in event_paths:
        print(f"\n----------------------------------------")
        print(f"【検証対象】: {path}")
        
        # 2. ファイルを正常に開けるか（パーミッションの検証）
        try:
            dev = InputDevice(path)
            print(f" └ [開く] 成功: デバイス名 = \"{dev.name}\"")
        except Exception as e:
            print(f" └ ❌ [開く] 失敗: 理由 = {e} (パーミッションエラーの可能性が高いです)")
            continue
            
        # 3. capabilities のデータ構造を抽出
        try:
            caps = dev.capabilities()
            print(f" └ [データ構造] 成功: 対応イベントタイプの生ID = {list(caps.keys())}")
            
            # 4. EV_KEY (値は 1) が含まれているか（鍵盤属性の検証）
            if ecodes.EV_KEY in caps:
                print(f"   └ ⭕ [属性確認]: このデバイスは「EV_KEY (鍵盤スイッチ)」に対応しています。")
                
                # 5. 型と要素数の実測値の検証
                supported_keys = caps[ecodes.EV_KEY]
                # 内部データの実際の型名を画面に割出出力
                print(f"   └ [型調査]: caps[ecodes.EV_KEY] の実際の型 = {type(supported_keys)}")
                
                # 安全に要素を全展開して個数を計測
                try:
                    raw_key_list = list(supported_keys)
                    key_count = len(raw_key_list)
                    print(f"   └ [個数計測]: 内部の有効キーコード総数 = {key_count} 個")
                except Exception as e:
                    print(f"   └ ❌ [個数計測] 破綻: リスト展開中にエラー = {e}")
                    key_count = -1
                    
                # 6. なぜ私の条件 (>= 100) で弾かれたのか、合致判定の実態を出力
                if key_count >= 100:
                    print(f"   └ ✨ [判定結果]: 条件成立！このデバイスを「メインキーボード」と認定できます。")
                else:
                    print(f"   └ ❌ [判定結果]: 条件不成立。キー総数 {key_count} が 100 未満のため弾かれました。")
                    
            else:
                print(f"   └ ❌ [属性確認]: このデバイスは EV_KEY に非対応です（マウスや音声ジャック等）。")
                
        except Exception as e:
            print(f" └ ❌ [データ構造解析] 致命的エラー: {e}")

    print("\n=== 解析・追跡調査終了 ===")

if __name__ == '__main__':
    main()

