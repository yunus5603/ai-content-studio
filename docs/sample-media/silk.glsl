float fb4(vec2 p){ float s=0.,a=.5; for(int i=0;i<4;i++){ s+=a*noise(p); p=M*p; a*=.5; } return s; }
vec3 pal(float t){ return .5+.5*cos(6.2831*(vec3(1.,1.,1.)*t+vec3(.0,.15,.3)+vec3(.8,.9,.95)*0.)); }
float pattern(vec2 p, float t, out vec2 q, out vec2 r){
  q=vec2(fb4(p+vec2(0.,0.)+t*.05),fb4(p+vec2(5.2,1.3)-t*.04));
  r=vec2(fb4(p+4.*q+vec2(1.7,9.2)+t*.08),fb4(p+4.*q+vec2(8.3,2.8)-t*.06));
  return fb4(p+4.*r);
}
void mainImage(out vec4 fragColor, vec2 fc){
  vec2 uv=fc/iResolution.y*.9;
  vec2 q,r; float t=iTime;
  float f=pattern(uv,t,q,r);
  vec2 q2,r2; float fx=pattern(uv+vec2(.004,0.),t,q2,r2), fy=pattern(uv+vec2(0.,.004),t,q2,r2);
  vec3 n=normalize(vec3((f-fx)*14.,(f-fy)*14.,1.));
  vec3 c1=vec3(1.,.42,.55), c2=vec3(.3,.28,.95), c3=vec3(1.,.72,.3), c4=vec3(.55,.95,1.);
  vec3 col=mix(c2,c1,smoothstep(.3,.7,f));
  col=mix(col,c3,clamp(length(q)*.9-.3,0.,1.)*.8);
  col=mix(col,c4,clamp(r.x*r.x*1.4,0.,1.)*.6);
  vec3 L=normalize(vec3(-.4,.6,.7));
  float dif=.6+.4*dot(n,L);
  float spec=pow(clamp(dot(reflect(-L,n),vec3(0,0,1)),0.,1.),24.);
  col=col*dif+spec*.35;
  col=pow(col,vec3(.9));
  fragColor=vec4(clamp(col,0.,1.),1.);
}
