 # fb_msg

 This is a small program that displays text to the /dev/fb0 for devices with no tty0, written by Gemini 2.5 Pro.

# Compiling

```sh
gcc -Os -s -ffunction-sections -fdata-sections -Wl,--gc-sections fb_msg.c -o fb_msg
gzip -9 -c fb_msg | base64 > fb_msg.b64
sed 's/^/echo "/; s/$/"/' fb_msg.b64 > fb_msg.sh
```

Insert the resulting `fb_msg.sh` into `makeself-header.sh`.

# License

Code is licensed under the [MIT License](LICENSE), PICO-8 font is licensed under the [Creative Commons CC0 1.0](https://creativecommons.org/publicdomain/zero/1.0/)

