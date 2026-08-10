#!/usr/bin/env python3
import sys
import glob
import termios
import tty
import os
import signal
from evdev import InputDevice, ecodes

def find_keyboard_device():
    """システム上の有効な物理キーボードデバイスを自動探索"""
    for path in glob.glob('/dev/input/event*'):
        try:
            dev = InputDevice(path)
            if ecodes.KEY_A in dev.capabilities().get(ecodes.EV_KEY, []):
                return dev
        except Exception:
            continue
    return None

def main():
    dev = find_keyboard_device()
    if not dev:
        print("エラー: 物理キーボードデバイスが見つかりません。", file=sys.stderr)
        sys.exit(1)

    # 1. ターミナルからの Ctrl+C シグナル（SIGINT）を完全に無視する設定に変更
    # これにより、終了処理中に非同期で KeyboardInterrupt が発生するのを100%防御します
    signal.signal(signal.SIGINT, signal.SIG_IGN)

    # 画面全体を一度綺麗にし、ヘッダー行を固定表示
    sys.stderr.write("\033[H\033[2J")
    sys.stderr.write("--- evdev 定数名調査モード ---\r\n")
    sys.stderr.write(f"使用デバイス: {dev.name} ({dev.path})\r\n")
    sys.stderr.write("調べたいキーを押してください。[Ctrl+C] で安全に終了します。\r\n\r\n")
    sys.stderr.flush()

    fd = sys.stdin.fileno()
    old_settings = termios.tcgetattr(fd)
    
    try:
        # 端末へのエコーバックを完全にシャットアウト
        tty.setraw(fd)
        
        ctrl_pressed = False
        
        # 物理イベントのループ
        for event in dev.read_loop():
            if event.type == ecodes.EV_KEY:
                keycode_name = ecodes.KEY.get(event.code, "UNKNOWN")
                
                if keycode_name in ('KEY_LEFTCTRL', 'KEY_RIGHTCTRL'):
                    ctrl_pressed = (event.value != 0)
                
                if event.value == 1: # Key Down
                    # 物理キーとして Ctrl + C が押されたことのみをトリガーにしてクリーンに終了する
                    if keycode_name == 'KEY_C' and ctrl_pressed:
                        break
                        
                    sys.stderr.write(f"\r\033[K定数名: {keycode_name}")
                    sys.stderr.flush()
                
    finally:
        # 2. 終了処理中はさらに強固にすべての重要シグナルをブロック
        signal.signal(signal.SIGINT, signal.SIG_IGN)
        
        # 端末の設定を元の正常なシェル環境へ完全に復元
        termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
        
        # デバイスを安全にクローズ（シグナルがマスクされているため、ここで絶対に中断されません）
        try:
            dev.close()
        except Exception:
            pass
            
        # 最終行を綺麗にしてプロンプトに戻る
        sys.stderr.write("\r\n\033[K正常に終了しました。\r\n")
        sys.stderr.flush()

if __name__ == '__main__':
    main()
