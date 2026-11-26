// SCENE 0 = alpine dawn, 1 = desert dunes
#ifndef SCENE
#define SCENE 0
#endif
float hash(vec2 p){ vec3 p3=fract(vec3(p.xyx)*.1031); p3+=dot(p3,p3.yzx+33.33); return fract((p3.x+p3.y)*p3.z); }
float noise(vec2 p){ vec2 i=floor(p),f=fract(p); vec2 u=f*f*(3.-2.*f);
  return mix(mix(hash(i),hash(i+vec2(1,0)),u.x),mix(hash(i+vec2(0,1)),hash(i+vec2(1,1)),u.x),u.y); }
const mat2 M=mat2(1.6,1.2,-1.2,1.6);
float H(vec2 p, int oct){
#if SCENE==0
  float h=0., a=.55; vec2 q=p*.09;
  for(int i=0;i<oct;i++){ float n=1.-abs(noise(q)*2.-1.); h+=a*n*n; q=M*q; a*=.48; }
  h = h*4.2-1.6;
  // valley along z
  h *= smoothstep(0.,6.,abs(p.x-sin(p.y*.08)*6.)) *.85+.15;
  return h;
#else
  vec2 q=p; q.x += noise(p*.05)*6.;
  float d = 0.;
  float r = sin(q.x*.35 + noise(p*.07)*3.); d += pow(1.-abs(r),1.6)*1.2;
  float r2 = sin(q.x*.9 + q.y*.3 + noise(p*.2)*2.); d += pow(1.-abs(r2),2.)*.25;
  float a=.08; vec2 s=p*.6; for(int i=0;i<oct;i++){ d+=a*noise(s); s=M*s; a*=.5; }
  return d*.9 - .2 + noise(p*.02)*1.5;
#endif
}
float march(vec3 ro, vec3 rd){ float t=.2; for(int i=0;i<220;i++){ vec3 p=ro+rd*t; float h=p.y-H(p.xz,6); if(abs(h)<.001*t||t>120.) break; t+=h*.45; } return t; }
vec3 nrm(vec3 p,float t){ vec2 e=vec2(.002*t,0); return normalize(vec3(H(p.xz-e.xy,9)-H(p.xz+e.xy,9),2.*e.x,H(p.xz-e.yx,9)-H(p.xz+e.yx,9))); }
float shadow(vec3 ro, vec3 rd){ float r=1., t=.1; for(int i=0;i<48;i++){ vec3 p=ro+rd*t; float h=p.y-H(p.xz,5); r=min(r,10.*h/t); t+=clamp(h,.2,2.); if(r<0.||t>40.) break; } return clamp(r,0.,1.); }
void mainImage(out vec4 fragColor, vec2 fc){
  vec2 uv=(fc-.5*iResolution.xy)/iResolution.y;
#if SCENE==0
  vec3 sun=normalize(vec3(.7,.3,-.9));
  vec3 skyTop=vec3(.18,.4,.85), skyHor=vec3(1.,.78,.62), sunCol=vec3(1.,.72,.45);
#else
  vec3 sun=normalize(vec3(-.8,.2,-.7));
  vec3 skyTop=vec3(.15,.42,.85), skyHor=vec3(.98,.86,.72), sunCol=vec3(1.,.82,.6);
#endif
  float z=iTime*1.4;
  vec3 ro=vec3(0.,0.,z); ro.y=max(H(ro.xz,4),0.)+ (SCENE==0?1.5:1.4);
  vec3 ta=vec3(sin(iTime*.1)*1.5, ro.y-.35, z+6.);
  vec3 ww=normalize(ta-ro), uu=normalize(cross(ww,vec3(0,1,0))), vv=cross(uu,ww);
  vec3 rd=normalize(uv.x*uu+uv.y*vv+1.6*ww);
  vec3 sky=mix(skyHor,skyTop,pow(clamp(rd.y+.05,0.,1.),.55));
  float sd=max(dot(rd,sun),0.);
  sky+=sunCol*pow(sd,6.)*.35+vec3(1.,.9,.8)*pow(sd,900.)*3.;
  // clouds
  if(rd.y>0.){ vec2 cp=rd.xz/rd.y*3.+iTime*.05; float c=0.,a=.5; for(int i=0;i<5;i++){c+=a*noise(cp);cp=M*cp;a*=.5;}
    c=smoothstep(.55,.9,c); sky=mix(sky,mix(vec3(1.),sunCol,.35)*1.05,c*.55*smoothstep(0.,.25,rd.y)); }
  vec3 col=sky;
  float t=march(ro,rd);
  if(t<120.){
    vec3 p=ro+rd*t; vec3 n=nrm(p,t);
    float dif=clamp(dot(n,sun),0.,1.); float sh=dif>0.?shadow(p+n*.05,sun):0.;
    float amb=.5+.5*n.y;
#if SCENE==0
    vec3 rock=mix(vec3(.28,.24,.22),vec3(.42,.36,.3),noise(p.xz*2.));
    vec3 grass=vec3(.22,.32,.18);
    vec3 alb=mix(grass,rock,smoothstep(.0,.9,p.y)*.8+ (1.-n.y)*1.2);
    float snow=smoothstep(.55,.85,n.y)*smoothstep(1.,1.8,p.y+noise(p.xz*1.5)*.6);
    alb=mix(alb,vec3(.95,.96,1.),snow);
#else
    vec3 alb=mix(vec3(.86,.6,.38),vec3(.95,.74,.5),noise(p.xz*.5));
    alb*= .9+.1*sin(p.x*40.+noise(p.xz*8.)*4.)*n.y; // ripples
#endif
    vec3 lin=dif*sh*sunCol*2.6 + amb*skyTop*.55 + clamp(dot(n,-vec3(sun.x,0,sun.z)),0.,1.)*skyHor*.12;
    col=alb*lin;
    float fog=1.-exp(-t*(SCENE==0?.016:.018));
    vec3 fogc=mix(skyHor,sunCol,pow(sd,4.)*.6);
    col=mix(col,fogc,fog);
  }
  col=1.-exp(-col*1.25); // tonemap
  col=pow(col,vec3(.92)); col=mix(vec3(dot(col,vec3(.299,.587,.114))),col,1.25); col=clamp(col,0.,1.);
  col*= .85+.15*pow(16.*fc.x*fc.y*(iResolution.x-fc.x)*(iResolution.y-fc.y)/pow(iResolution.x*iResolution.y,2.),.15);
  fragColor=vec4(col,1.);
}
