```sh
sudo apt install python3-evdev
```

a.py
```python
#!/usr/bin/env python3
# read_keys.py
from evdev import InputDevice, categorize, ecodes

# ※適切なevent番号に書き換えてください（evtest等で確認可能）
device = InputDevice('/dev/input/event0') 

print(f"Listening on {device.name}...")
for event in device.read_loop():
    if event.type == ecodes.EV_KEY:
        key_event = categorize(event)
        if key_event.keystate == 1: # 1: Key Down
            if key_event.keycode == 'KEY_MUHENKAN':
                print("【無変換】が押されました")
            elif key_event.keycode == 'KEY_HENKAN':
                print("【変換】が押されました")
```
```sh
$ ./a.py
Listening on SIGMACHIP USB Keyboard...
【無変換】が押されました
【変換】が押されました
```


