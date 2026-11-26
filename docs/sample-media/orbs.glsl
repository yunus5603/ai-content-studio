// pastel studio product shot: orbs + torus on a curved cyclorama
float sdTorus(vec3 p, vec2 t){ vec2 q=vec2(length(p.xz)-t.x,p.y); return length(q)-t.y; }
mat2 rot(float a){ float c=cos(a),s=sin(a); return mat2(c,-s,s,c); }
vec2 map(vec3 p){
  vec2 r=vec2(p.y+0.,0.); // floor id 0
  float b=iTime*1.2;
  float s1=length(p-vec3(-1.15,.75+sin(b)*.08,.3))-.75; if(s1<r.x) r=vec2(s1,1.);
  float s2=length(p-vec3(.9,.5+sin(b+2.)*.08,-.5))-.5; if(s2<r.x) r=vec2(s2,2.);
  float s3=length(p-vec3(.35,.28+sin(b+4.)*.05,.95))-.28; if(s3<r.x) r=vec2(s3,3.);
  vec3 q=p-vec3(-.3,1.05+sin(b+1.)*.1,-1.5); q.yz*=rot(1.1+iTime*.4); q.xy*=rot(.4);
  float t=sdTorus(q,vec2(.42,.13)); if(t<r.x) r=vec2(t,4.);
  return r;
}
vec3 calcN(vec3 p){ vec2 e=vec2(.001,0); return normalize(vec3(map(p+e.xyy).x-map(p-e.xyy).x,map(p+e.yxy).x-map(p-e.yxy).x,map(p+e.yyx).x-map(p-e.yyx).x)); }
float soft(vec3 ro, vec3 rd){ float r=1.,t=.02; for(int i=0;i<64;i++){ float h=map(ro+rd*t).x; r=min(r,8.*h/t); t+=clamp(h,.01,.2); if(r<.001||t>8.) break;} return clamp(r,0.,1.); }
float ao(vec3 p, vec3 n){ float o=0.,s=1.; for(int i=1;i<6;i++){ float h=.04*float(i); o+=(h-map(p+n*h).x)*s; s*=.75; } return clamp(1.-2.5*o,0.,1.); }
vec3 albedo(float id, vec3 p){
  if(id<.5) return vec3(.93,.8,.78);
  if(id<1.5) return vec3(1.,.62,.55);
  if(id<2.5) return vec3(.62,.6,1.);
  if(id<3.5) return vec3(.55,.9,.78);
  return vec3(1.,.82,.45);
}
vec3 bg(vec3 rd){ return mix(vec3(.96,.8,.78),vec3(.86,.8,.96),clamp(rd.y*2.+.5,0.,1.)); }
vec3 shade(vec3 ro, vec3 rd, out vec3 hitP, out vec3 hitN, out float hitId, out bool hit){
  float t=0.; vec2 h; hit=false;
  for(int i=0;i<160;i++){ h=map(ro+rd*t); if(h.x<.0005){hit=true;break;} t+=h.x; if(t>30.) break; }
  if(!hit){ return bg(rd); }
  vec3 p=ro+rd*t; vec3 n=calcN(p); hitP=p; hitN=n; hitId=h.y;
  vec3 L=normalize(vec3(-.5,.9,.4));
  float dif=clamp(dot(n,L),0.,1.)*soft(p+n*.002,L);
  float occ=ao(p,n);
  vec3 alb=albedo(h.y,p);
  vec3 col=alb*(dif*vec3(1.,.96,.92)*.95 + occ*(.38+.2*n.y)*vec3(.95,.9,1.));
  float spec=pow(clamp(dot(reflect(rd,n),L),0.,1.),60.)*dif;
  col+=spec*(h.y>.5?.8:.05);
  col+= alb*.25*clamp(1.+dot(rd,n),0.,1.)*occ; // rim
  float fog=1.-exp(-max(t-4.,0.)*.08); col=mix(col,bg(rd),fog);
  return col;
}
void mainImage(out vec4 fragColor, vec2 fc){
  vec2 uv=(fc-.5*iResolution.xy)/iResolution.y;
  float a=.35+sin(iTime*.25)*.25;
  vec3 ro=vec3(5.2*sin(a),2.3,5.2*cos(a)); vec3 ta=vec3(0.,.6,.3);
  vec3 ww=normalize(ta-ro), uu=normalize(cross(ww,vec3(0,1,0))), vv=cross(uu,ww);
  vec3 rd=normalize(uv.x*uu+uv.y*vv+2.2*ww);
  vec3 p,n; float id; bool hit;
  vec3 col=shade(ro,rd,p,n,id,hit);
  if(hit && id>.5){ // one glossy bounce
    vec3 p2,n2; float id2; bool h2; vec3 r=reflect(rd,n);
    vec3 rc=shade(p+n*.01,r,p2,n2,id2,h2);
    float fr=.04+.5*pow(1.-clamp(dot(-rd,n),0.,1.),4.);
    col=mix(col,rc,fr*(id>3.5?1.6:1.));
  }
  col=pow(col,vec3(.95));
  vec2 q=fc/iResolution.xy; col*=.88+.12*pow(16.*q.x*q.y*(1.-q.x)*(1.-q.y),.2);
  fragColor=vec4(clamp(col,0.,1.),1.);
}
