#!/usr/bin/env python3
import glob
import sys
from evdev import InputDevice, ecodes

def main():
    target_device = None
    
    for path in sorted(glob.glob('/dev/input/event*')):
        try:
            dev = InputDevice(path)
            caps = dev.capabilities()
            
            # 1. 鍵盤イベント(EV_KEY)をサポートしているか
            if ecodes.EV_KEY in caps:
                # 2. 文字入力用の通常キーボード (KEY_A) が内部スロットに実在しているかを評価
                if ecodes.KEY_A in caps[ecodes.EV_KEY]:
                    target_device = dev
                    break # 本物のメインノードを特定したので走査を終了
        except Exception:
            continue
            
    if target_device is not None:
        # 修正の事実: 存在しない .id プロパティを撤去し、正しい .info を使用
        info = target_device.info
        print(f"発見ノード    : {target_device.path}", flush=True)
        print(f"デバイス名    : {target_device.name}", flush=True)
        print(f"ベンダーID    : 0x{info.vendor:04x}", flush=True)
        print(f"プロダクトID  : 0x{info.product:04x}", flush=True)
        print(f"固有識別子候補: USB_{info.vendor:04x}_{info.product:04x}", flush=True)
        sys.exit(0)
    else:
        print("エラー: USB HID Keyboard デバイスを特定できませんでした。一般権限の場合は input グループに属しているかを確認、または sudo で実行してください。", file=sys.stderr)
        sys.exit(1)

if __name__ == '__main__':
    main()
