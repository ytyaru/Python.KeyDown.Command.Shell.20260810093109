#!/usr/bin/env python3
import sys
import glob
import termios
import tty
import os
from evdev import InputDevice, ecodes

class DeviceManager:
    """物理デバイスの探索とクローズのみを担当"""
    @staticmethod
    def find_keyboard():
        for path in glob.glob('/dev/input/event*'):
            try:
                dev = InputDevice(path)
                if ecodes.KEY_A in dev.capabilities().get(ecodes.EV_KEY, []):
                    return dev
            except Exception:
                continue
        return None

class TerminalContext:
    """端末の生モード設定とバッファの完全消去のみを担当"""
    def __init__(self):
        self.fd = sys.stdin.fileno()
        self.old_settings = termios.tcgetattr(self.fd)

    def enter_raw_mode(self):
        # 生モードの基本設定
        tty.setraw(self.fd)
        # 追加割込抑止: ISIGをオフにしてCtrl+Cによるエコー文字出力を物理的に遮断
        new_settings = termios.tcgetattr(self.fd)
        new_settings[3] &= ~termios.ISIG
        termios.tcsetattr(self.fd, termios.TCSANOW, new_settings)

    def exit_and_flush(self):
        # 画面に出力されかかっている、またはバッファに溜まっている制御文字(^Cなど)を完全破棄
        termios.tcflush(sys.stdout.fileno(), termios.TCIOFLUSH)
        # 端末設定の復元
        termios.tcsetattr(self.fd, termios.TCSADRAIN, self.old_settings)

class ScreenRenderer:
    """画面への描画処理のみを担当（すべて標準エラー出力）"""
    @staticmethod
    def clear_all():
        sys.stderr.write("\033[H\033[2J")
        sys.stderr.flush()

    @staticmethod
    def draw_header():
        sys.stderr.write("--- evdev 定数名調査モード ---\r\n")
        sys.stderr.write("調べたいキーを押してください。 [Ctrl+C]:終了  [Ctrl+S]:保存\r\n\r\n")
        sys.stderr.flush()

    @staticmethod
    def draw_status(current_key, last_target, is_saved=False):
        # \r\033[K で行をクリアし、\033[A で上の行に戻る固定配置描画
        sys.stderr.write(f"\r\033[K定数名: {current_key}\r\n\033[K")
        if is_saved:
            sys.stderr.write(f"\033[32m[保存完了]: {last_target}\033[0m")
        elif current_key in ('KEY_LEFTCTRL', 'KEY_RIGHTCTRL') and last_target:
            sys.stderr.write(f"[直前]: {last_target}  (Ctrl+Sでこれを保存します)")
        sys.stderr.write("\033[A")
        sys.stderr.flush()

class KeycodeInvestigator:
    """イベントループと状態管理のみを担当"""
    def __init__(self, dev):
        self.dev = dev
        self.saved_log = []
        self.last_target = None

    def start_loop(self):
        ctrl_pressed = False
        
        for event in self.dev.read_loop():
            if event.type != ecodes.EV_KEY:
                continue
                
            keycode_name = ecodes.KEY.get(event.code, "UNKNOWN")
            
            if keycode_name in ('KEY_LEFTCTRL', 'KEY_RIGHTCTRL'):
                ctrl_pressed = (event.value != 0)
            
            if event.value == 1:  # Key Down
                if keycode_name == 'KEY_C' and ctrl_pressed:
                    break
                elif keycode_name == 'KEY_S' and ctrl_pressed:
                    if self.last_target:
                        self.saved_log.append(self.last_target)
                        ScreenRenderer.draw_status(keycode_name, self.last_target, is_saved=True)
                    continue
                
                if keycode_name not in ('KEY_LEFTCTRL', 'KEY_RIGHTCTRL'):
                    self.last_target = keycode_name
                    
                ScreenRenderer.draw_status(keycode_name, self.last_target, is_saved=False)

    def get_results(self):
        return self.saved_log

def main():
    dev = DeviceManager.find_keyboard()
    if not dev:
        print("エラー: 物理キーボードデバイスが見つかりません。", file=sys.stderr)
        sys.exit(1)

    term = TerminalContext()
    investigator = KeycodeInvestigator(dev)

    ScreenRenderer.clear_all()
    ScreenRenderer.draw_header()
    term.enter_raw_mode()

    try:
        investigator.start_loop()
    finally:
        term.exit_and_flush()
        ScreenRenderer.clear_all()
        try:
            dev.close()
        except Exception:
            pass

    # 最終結果データのみを標準出力へ出力
    for log_item in investigator.get_results():
        print(log_item, flush=True)

if __name__ == '__main__':
    main()
