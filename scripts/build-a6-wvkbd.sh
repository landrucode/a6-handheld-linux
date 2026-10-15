#!/usr/bin/env bash
set -euo pipefail
repo=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
source_dir="$repo/.deps/wvkbd"
revision=6b41504a0cb58fd1163fa44692398fbd61f8905f
[[ $(git -C "$source_dir" rev-parse HEAD) == "$revision" ]]
sysroot="$repo/build/aquamarine-sysroot"
profile=${A6_WVKBD_PROFILE:-baseline}
[[ "$profile" == baseline || "$profile" == native ]]
if [[ "$profile" == native ]]; then
  export A6_WVKBD_REDRAW_CANDIDATE=1 A6_WVKBD_BOTTOM_MARGIN=0
fi
position=${A6_WVKBD_POSITION:-bottom}
[[ "$position" == bottom || "$position" == top ]]
stage="$repo/build/wvkbd-src-$position"
output="$repo/build/arm/wvkbd-mobintl"
[[ "$position" == bottom ]] || output="$repo/build/arm/wvkbd-mobintl-top"
if [[ "$profile" == native ]]; then
  [[ "$position" == bottom ]]
  output="$repo/build/arm/wvkbd-native"
fi
mkdir -p "$stage" "$repo/build/arm"
git -C "$source_dir" archive "$revision" | tar -x -C "$stage"
if [[ "$position" == top ]]; then
  python3 - "$stage/main.c" <<'PYTOP'
import sys
from pathlib import Path
p = Path(sys.argv[1])
s = p.read_text()
anchor = 'static uint32_t anchor = ZWLR_LAYER_SURFACE_V1_ANCHOR_BOTTOM |'
assert s.count(anchor) == 1
p.write_text(s.replace(anchor, anchor.replace('ANCHOR_BOTTOM', 'ANCHOR_TOP')))
PYTOP
fi
# Experimental redraw/popup candidate; baseline remains unchanged.
if [[ ${A6_WVKBD_REDRAW_CANDIDATE:-0} == 1 ]]; then
python3 - "$stage/drw.c" <<'PYDAMAGE'
import sys
from pathlib import Path
p = Path(sys.argv[1])
s = p.read_text()
a = '    wl_surface_attach(ds->surf, ds->back_buffer->buf, 0, 0);'
assert s.count(a) == 1
s = s.replace(a, a + '\n    if (!ds->attached)\n        wl_surface_damage(ds->surf, 0, 0, ds->width, ds->height);')
# Native candidate submits accumulated damage before sleeping instead of
# waiting for a frame on an unchanged surface (which may never be scheduled).
if __import__('os').environ.get('A6_WVKBD_DIRECT_DAMAGE', '0') == '1':
    s = s.replace('    drwsurf_register_frame_cb(ds);', '    /* Submitted once at the event-loop boundary. */')
    s += '''
void drwsurf_submit_damage(struct drwsurf *ds) {
    if (!ds->attached || cairo_region_is_empty(ds->damage)) return;
    cairo_rectangle_int_t r;
    for (int i=0;i<cairo_region_num_rectangles(ds->damage);i++) {
        cairo_region_get_rectangle(ds->damage,i,&r);
        wl_surface_damage(ds->surf,r.x,r.y,r.width,r.height);
    }
    cairo_region_subtract(ds->damage,ds->damage);
    drwsurf_attach(ds);
}
'''
p.write_text(s)
p = Path(sys.argv[1]).with_name('main.c')
s = p.read_text()
a = '    popup_draw_surf.surf = wl_compositor_create_surface(compositor);'
z = '    wl_surface_commit(popup_draw_surf.surf);'
assert s.count(a) == s.count(z) == 1
start, end = s.index(a), s.index(z) + len(z)
s = s[:start] + '    if (keyboard.show_popup) {\n' + s[start:end] + '\n    } else {\n        popup_xdg_surface_configured = true;\n    }' + s[end:]
# Draw again after the compositor's first frame, without injecting input.
a = 'void\nlayer_surface_configure(void *data, struct zwlr_layer_surface_v1 *surface,'
assert s.count(a) == 1
helper = '''static void initial_layout_done(void *data, struct wl_callback *callback, uint32_t time)
{
    wl_callback_destroy(callback);
    kbd_draw_layout(&keyboard);
    wl_surface_damage(draw_surf.surf, 0, 0, draw_surf.width, draw_surf.height);
    drwsurf_attach(&draw_surf);
}
static const struct wl_callback_listener initial_layout_listener = {
    .done = initial_layout_done,
};

'''
s = s.replace(a, helper + a)
a = '    kbd_resize(&keyboard, layouts, NumLayouts);\n    drwsurf_attach(&draw_surf);'
assert s.count(a) == 1
s = s.replace(a, a + '\n    struct wl_callback *initial = wl_surface_frame(draw_surf.surf);\n    wl_callback_add_listener(initial, &initial_layout_listener, NULL);\n    wl_surface_commit(draw_surf.surf);')
import os
if os.environ.get('A6_WVKBD_POLL_CANDIDATE', '0') == '1':
    # The upstream multi-statement die macro must be safe in unbraced checks.
    start = s.index('#define die(')
    end = s.index('/* array size */', start)
    s = s[:start] + '#define die(...) do { fprintf(stderr, __VA_ARGS__); exit(1); } while (0)\n\n' + s[end:]
    # Drain buffered events before sleeping, and pair every prepared read with
    # read_events/cancel_read, including signals, EINTR and a full output socket.
    a = ('        wl_display_flush(display);\n'
         '        poll(fds, 2, -1);\n\n'
         '        if (fds[WAYLAND_FD].revents & POLLIN)\n'
         '            wl_display_dispatch(display);')
    b = """        while (wl_display_prepare_read(display) != 0) {
                if (wl_display_dispatch_pending(display) < 0)
                    die("Wayland pending dispatch failed\\n");
            }
            if (!run_display) {
                wl_display_cancel_read(display);
                break;
            }
            fds[WAYLAND_FD].events = POLLIN;
            if (wl_display_flush(display) < 0) {
                if (errno == EAGAIN)
                    fds[WAYLAND_FD].events |= POLLOUT;
                else {
                    wl_display_cancel_read(display);
                    die("Wayland flush failed\\n");
                }
            }
            int ready = poll(fds, 2, -1);
            if (ready < 0) {
                wl_display_cancel_read(display);
                if (errno == EINTR)
                    continue;
                die("Wayland poll failed\\n");
            }
            if (fds[WAYLAND_FD].revents & POLLIN) {
                if (wl_display_read_events(display) < 0)
                    die("Wayland read failed\\n");
            } else {
                wl_display_cancel_read(display);
            }
            if (wl_display_dispatch_pending(display) < 0)
                die("Wayland dispatch failed\\n");"""
    assert s.count(a) == 1
    s = s.replace(a, b)
if os.environ.get('A6_WVKBD_DIRECT_DAMAGE', '0') == '1':
    s = s.replace('    while (run_display) {', '''    extern void drwsurf_submit_damage(struct drwsurf *);
    while (run_display) {
        if (wl_display_dispatch_pending(display) < 0) die("Pending dispatch failed\\n");
        drwsurf_submit_damage(&draw_surf);
        if (keyboard.show_popup) drwsurf_submit_damage(&popup_draw_surf);''')
p.write_text(s)
p = p.with_name('keyboard.c')
s = p.read_text()
a = '    drwsurf_resize(kb->popup_surf, kb->w, kb->h * 2, kb->scale);'
assert s.count(a) == 1
s = s.replace(a, '    if (kb->show_popup)\n' + a)
p.write_text(s)
PYDAMAGE
fi
# Optional interior placement for edge-calibration trials.
margin=${A6_WVKBD_BOTTOM_MARGIN:-0}
[[ "$margin" =~ ^[0-9]+$ && "$margin" -le 300 ]]
if [[ "$margin" != 0 ]]; then
  python3 - "$stage/main.c" "$margin" <<'PYMARGIN'
import sys
from pathlib import Path
p = Path(sys.argv[1])
s = p.read_text()
a = '    zwlr_layer_surface_v1_set_anchor(layer_surface, anchor);'
assert s.count(a) == 1
s = s.replace(a, a + '\n    zwlr_layer_surface_v1_set_margin(layer_surface, 0, 0, ' + sys.argv[2] + ', 0);')
p.write_text(s)
PYMARGIN
fi
export PKG_CONFIG_SYSROOT_DIR="$sysroot"
export PKG_CONFIG_LIBDIR="$sysroot/usr/lib/pkgconfig:$sysroot/usr/share/pkgconfig"
pkg-config --exists wayland-client xkbcommon pangocairo
make -C "$stage" clean
compiler="clang -ffile-prefix-map=$repo=. -fdebug-prefix-map=$repo=. --target=arm-linux-gnueabihf --sysroot=$sysroot --gcc-install-dir=$sysroot/usr/lib/gcc/armv7l-unknown-linux-gnueabihf/16.1.1 -march=armv7-a -mfpu=neon -mfloat-abi=hard -fuse-ld=lld -O2 -fPIE -fstack-protector-strong -D_FORTIFY_SOURCE=2"
make -C "$stage" -j4 wvkbd-mobintl CC="$compiler" LDFLAGS="$(pkg-config --libs wayland-client xkbcommon pangocairo) -lm -lutil -lrt -pie -Wl,-z,relro,-z,now"
llvm-strip --strip-debug -o "$output" "$stage/wvkbd-mobintl"
sha256sum "$output"
