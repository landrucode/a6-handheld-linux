-- Native A6 software-rendered desktop; run as user1000.
hl.monitor({ output = "", mode = "preferred", position = "auto", scale = 1 })
hl.config({
    general = {
        gaps_in = 0, gaps_out = 0, border_size = 1,
        ["col.active_border"] = "rgb(c9b6f2)",
        ["col.inactive_border"] = "rgb(3e3a4c)",
    },
    misc = {
        background_color = "rgb(26242e)",
        disable_hyprland_logo = true,
        disable_splash_rendering = true,
        force_default_wallpaper = 0,
    },
    decoration = { rounding = 0, blur = { enabled = false }, shadow = { enabled = false } },
    animations = { enabled = false },
    input = { repeat_rate = 0, follow_mouse = 0, touchdevice = { transform = -1 } },
    xwayland = { enabled = false },
    -- Verified config keys in Hyprland0.56. Apply before the first frame.
    debug = { vfr = true },
    render = { cm_enabled = true, use_fp16 = 2, new_render_scheduling = false },
    cursor = { no_hardware_cursors = 2 },
})
hl.on("hyprland.start", function () hl.exec_cmd("foot /bin/bash") end)
