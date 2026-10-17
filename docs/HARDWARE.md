# Logitech G13 — what the kernel exposes (hid-lg-g15, Linux ≥ 6.19)

USB `046d:c21c`, one HID interface, interrupt IN 8 bytes, interrupt OUT 64 bytes.

## HID report descriptor (vendor page 0xFF00)

| Report | Dir | Size | Use |
|---|---|---|---|
| 1 | input | 7 | keys bitmap + stick (handled by the kernel) |
| 3 | output | 991 | LCD framebuffer |
| 4 | feature | 4 | unknown |
| 5 | feature | 4 | M-key LEDs (kernel) |
| 6 | feature | 257 | unknown |
| 7 | feature | 4 | RGB backlight (kernel) |

## Input devices

`Logitech G13 Gaming Keypad` (keyboard-like):

| Control | evdev code |
|---|---|
| G1..G22 | `KEY_MACRO1`..`KEY_MACRO22` |
| LCD buttons left→right | `KEY_KBD_LCD_MENU1`..`MENU4` |
| round "menu" button | `KEY_KBD_LCD_MENU5` |
| M1 M2 M3 MR | `KEY_MACRO_PRESET1..3`, `KEY_MACRO_RECORD_START` |
| backlight button | `KEY_LIGHTS_TOGGLE` (the hardware toggles the light itself) |

`Logitech G13 Thumbstick` (joystick-like, gets `uaccess` from the stock joystick udev rules):
`ABS_X`, `ABS_Y` 0..255 (centre ≈ 128), `BTN_THUMB` (stick press), `BTN_BASE` (left button),
`BTN_BASE2` (bottom button).

## LEDs (`/sys/class/leds/`)

`g13:red:macro_preset_1..3`, `g13:red:macro_record` (0/1), `g13:rgb:kbd_backlight`
(`multi_intensity = "r g b"`, `brightness` 0..255, `brightness_hw_changed` reflects the light button).
The G13 forgets everything at power loss: reapply on every connect.

## LCD

160×43 monochrome, written through `/dev/hidrawN` as one 992-byte output report:
`0x03`, 31 zero bytes, then 960 pixel bytes with `index = 32 + x + (y // 8) * 160`, `bit = y % 8`
(bit 0 = topmost row of the 8-pixel band). Validated 2026-10-17 on firmware `bcdDevice 2.03`.
