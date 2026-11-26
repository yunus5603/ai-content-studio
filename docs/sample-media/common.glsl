float hash(vec2 p){ vec3 p3=fract(vec3(p.xyx)*.1031); p3+=dot(p3,p3.yzx+33.33); return fract((p3.x+p3.y)*p3.z); }
float noise(vec2 p){ vec2 i=floor(p),f=fract(p); vec2 u=f*f*(3.-2.*f);
  return mix(mix(hash(i),hash(i+vec2(1,0)),u.x),mix(hash(i+vec2(0,1)),hash(i+vec2(1,1)),u.x),u.y); }
const mat2 M=mat2(1.6,1.2,-1.2,1.6);
float fbm(vec2 p){ float s=0.,a=.5; for(int i=0;i<6;i++){ s+=a*noise(p); p=M*p; a*=.5; } return s; }
vec3 post(vec3 col, vec2 fc){ col=1.-exp(-col*1.2); col=mix(vec3(dot(col,vec3(.299,.587,.114))),col,1.15);
  vec2 q=fc/iResolution.xy; col*=.8+.2*pow(16.*q.x*q.y*(1.-q.x)*(1.-q.y),.2); return clamp(col,0.,1.); }
