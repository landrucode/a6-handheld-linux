# Pastel theme

The desktop's own colour theme. `palette.sh` is the single source of colours.

- `foot.ini`: terminal colours and font (JetBrains Mono, size 14).
- `wvkbd.args`: on-screen keyboard colours.
- The panel sources `palette.sh`.
- The image builder generates labwc's `themerc-override` from `palette.sh`.
  `rootfs/labwc/rc.xml` selects the theme, keeps apps maximised and turns
  off window decorations.
- labwc's autostart uses `swaybg` to paint the background in `A6_BG`.
