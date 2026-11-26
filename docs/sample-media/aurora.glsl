vec3 skyAt(vec3 rd){
  vec3 col=mix(vec3(.02,.04,.1),vec3(.01,.015,.04),clamp(rd.y*1.5,0.,1.));
  // stars
  vec2 sp=rd.xy/(rd.z+1.)*300.; float s=hash(floor(sp)); col+=vec3(.9,.95,1.)*step(.996,s)*smoothstep(.5,0.,length(fract(sp)-.5))*2.;
  vec2 a=vec2(rd.x/rd.z, rd.y);
  vec3 acc=vec3(0.);
  for(int k=0;k<3;k++){
    float fk=float(k);
    float x=a.x*(1.+fk*.3)+fk*1.7;
    float yc=.36+fk*.1+sin(x*1.6+iTime*.15+fk)*.07+(fbm(vec2(x*.9+iTime*.05,fk*3.))-.5)*.25;
    float d=a.y-yc;
    float rays=.35+.65*pow(noise(vec2(x*55.+fbm(vec2(x*3.,iTime*.2))*6.,fk*7.+iTime*.3)),1.5);
    float body=smoothstep(-.015,.0,d)*exp(-max(d,0.)*(11.-fk*2.));
    vec3 tint=mix(vec3(.15,1.,.55),vec3(.2,.9,.9),fk*.4);
    vec3 top=vec3(.75,.25,1.);
    acc+= mix(tint,top,smoothstep(.0,.25,d))*body*rays*(1.1-fk*.3)*smoothstep(.25,.6,fbm(vec2(x*.4+fk,iTime*.03)));
  }
  col+=acc*smoothstep(0.,.1,rd.y)*.9; col+=vec3(.05,.25,.2)*exp(-abs(a.y-.3)*4.)*.25;
  return col;
}
void mainImage(out vec4 fragColor, vec2 fc){
  vec2 uv=(fc-.5*iResolution.xy)/iResolution.y;
  vec3 rd=normalize(vec3(uv.x,uv.y+.28,1.));
  vec3 col;
  // mountain silhouette
  float mh = .04 + fbm(vec2(uv.x*2.5+3.,1.))*.22 - .08 + fbm(vec2(uv.x*14.,5.))*.025;
  float far = .02 + fbm(vec2(uv.x*1.6+9.,2.))*.14;
  float horizon=-.12;
  if(uv.y>horizon){
    col=skyAt(rd);
    float y=uv.y-horizon;
    col=mix(col,vec3(.02,.03,.06)+skyAt(normalize(vec3(uv.x,.2,1.)))*.15,step(y,far));
    col=mix(col,vec3(.005,.01,.02),step(y,mh*.9));
  } else {
    // lake reflection with ripples
    float y=horizon-uv.y;
    vec2 r=vec2(uv.x+ (fbm(vec2(uv.x*8.,y*25.-iTime*.6))-.5)*.006*y*8., horizon+y);
    vec3 rrd=normalize(vec3(r.x,r.y+.28,1.));
    vec3 rc=skyAt(rrd);
    float ry=y; 
    float m=.04 + fbm(vec2(r.x*2.5+3.,1.))*.22 - .08 + fbm(vec2(r.x*14.,5.))*.025;
    float f2=.02 + fbm(vec2(r.x*1.6+9.,2.))*.14;
    rc=mix(rc,vec3(.02,.03,.06),step(ry,f2));
    rc=mix(rc,vec3(.005,.01,.02),step(ry,m*.9));
    col=rc*.55;
  }
  fragColor=vec4(post(col*1.3,fc),1.);
}
