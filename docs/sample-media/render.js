// usage: node render.js shader.glsl W H outPrefix startT frames fps [defines]
const { chromium } = require('playwright');
const fs = require('fs');
const [,, shaderPath, W, H, out, startT='0', frames='1', fps='24', defines=''] = process.argv;
const src = fs.readFileSync(shaderPath, 'utf8');
(async () => {
  const b = await chromium.launch({ args: ['--use-angle=swiftshader', '--enable-unsafe-swiftshader'] });
  const p = await b.newPage();
  p.on('console', m => console.log('page:', m.text()));
  await p.setContent('<canvas id=c></canvas>');
  const err = await p.evaluate(({ src, W, H, defines }) => {
    const c = document.getElementById('c'); c.width = W; c.height = H;
    const gl = c.getContext('webgl2', { preserveDrawingBuffer: true, antialias: false });
    const vs = `#version 300 es
in vec2 p; void main(){ gl_Position = vec4(p,0.,1.); }`;
    const fs = `#version 300 es
precision highp float;
uniform vec3 iResolution; uniform float iTime; out vec4 outColor;
${defines.split(',').filter(Boolean).map(d => '#define ' + d.replace('=', ' ')).join('\n')}
${src}
void main(){ vec4 col; mainImage(col, gl_FragCoord.xy); outColor = vec4(col.rgb, 1.); }`;
    function sh(t, s) { const o = gl.createShader(t); gl.shaderSource(o, s); gl.compileShader(o); if (!gl.getShaderParameter(o, gl.COMPILE_STATUS)) throw new Error(gl.getShaderInfoLog(o)); return o; }
    try {
      const pr = gl.createProgram(); gl.attachShader(pr, sh(gl.VERTEX_SHADER, vs)); gl.attachShader(pr, sh(gl.FRAGMENT_SHADER, fs)); gl.linkProgram(pr); gl.useProgram(pr);
      const buf = gl.createBuffer(); gl.bindBuffer(gl.ARRAY_BUFFER, buf);
      gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1, -1, 3, -1, -1, 3]), gl.STATIC_DRAW);
      const loc = gl.getAttribLocation(pr, 'p'); gl.enableVertexAttribArray(loc); gl.vertexAttribPointer(loc, 2, gl.FLOAT, false, 0, 0);
      window.__draw = (t) => { gl.viewport(0, 0, W, H); gl.uniform3f(gl.getUniformLocation(pr, 'iResolution'), W, H, 1); gl.uniform1f(gl.getUniformLocation(pr, 'iTime'), t); gl.drawArrays(gl.TRIANGLES, 0, 3); gl.finish(); return c.toDataURL('image/png'); };
      return null;
    } catch (e) { return e.message; }
  }, { src, W: +W, H: +H, defines });
  if (err) { console.error(err); process.exit(1); }
  const n = +frames;
  for (let i = 0; i < n; i++) {
    const t = +startT + i / +fps;
    const d = await p.evaluate(t => window.__draw(t), t);
    const name = n === 1 ? `${out}.png` : `${out}_${String(i).padStart(4, '0')}.png`;
    fs.writeFileSync(name, Buffer.from(d.split(',')[1], 'base64'));
  }
  await b.close();
})();
