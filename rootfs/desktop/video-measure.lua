-- Public counters only: never record media URLs or titles.
local mp = require 'mp'
local file = io.open('/tmp/a6-video-measure.private.log', 'a')
local previous_ticks, previous_time = nil, nil
local latest = {width=0,height=0,drops=0,decoder_drops=0}
local function cpu_ticks()
    local stat = io.open('/proc/self/stat', 'r')
    if not stat then return nil end
    local data = stat:read('*a'); stat:close()
    local rest = data:match('^.*%) (.*)$'); if not rest then return nil end
    local fields = {}; for word in rest:gmatch('%S+') do fields[#fields+1]=word end
    return tonumber(fields[12])+tonumber(fields[13])
end
for name,key in pairs({width='width',height='height',['frame-drop-count']='drops',
                      ['decoder-frame-drop-count']='decoder_drops'}) do
    mp.observe_property(name, 'number', function(_,value)
        if value and mp.get_property_number('width',0)>0 then latest[key]=value end
    end)
end
local function sample(phase)
    if not file then return end
    local now, ticks = mp.get_time(), cpu_ticks()
    local cpu = previous_ticks and ticks and now > previous_time and
                ((ticks-previous_ticks)/(now-previous_time)) or 0
    previous_ticks, previous_time = ticks, now
    file:write(string.format('phase=%s cpu_percent=%.1f time=%.3f width=%s height=%s drops=%s decoder_drops=%s\n',
        phase or 'sample', cpu, now, latest.width,latest.height,latest.drops,latest.decoder_drops))
    file:flush()
end
mp.add_periodic_timer(1, sample)
mp.register_event('end-file', function() sample('end') end)
mp.register_event('shutdown', function() sample('shutdown'); if file then file:close(); file=nil end end)
