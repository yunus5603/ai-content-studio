# Sample media

The showcase images and loops in `frontend/public/samples/` are original procedural renders
made for this project from the GLSL shaders in this folder. No stock footage or third-party
assets are involved, so there is nothing to license or attribute. They are illustrative
examples, not outputs of the generation models; swap in real generations any time by
replacing the files and updating `frontend/src/lib/samples.ts`.

## Re-render

Needs Node with Playwright (Chromium) and ffmpeg.

```bash
cat common.glsl aurora.glsl > /tmp/aurora.glsl          # aurora, silk and planet use common.glsl
node render.js /tmp/aurora.glsl 3200 1800 /tmp/aurora 2  # still frame at t=2s
node render.js terrain.glsl 3200 1800 /tmp/dunes 3 1 24 SCENE=1
node render.js orbs.glsl 1920 1080 /tmp/orbs/f 0 144 24  # 6 s of frames for a loop
```

Loops were encoded at 1280x720 with a 1 s crossfade from the end back to the start, so they
repeat seamlessly:

```bash
ffmpeg -framerate 24 -i f_%04d.png -filter_complex \
  "[0]scale=1280:720,split[a][b];[a]trim=1:6,setpts=PTS-STARTPTS[m];[b]trim=0:1,setpts=PTS-STARTPTS[h];[m][h]xfade=duration=1:offset=4,format=yuv420p" \
  -c:v libx264 -crf 25 -movflags +faststart -an loop.mp4
```
