vec2 sph(vec3 ro, vec3 rd, float r){ float b=dot(ro,rd), c=dot(ro,ro)-r*r, h=b*b-c; if(h<0.) return vec2(-1.); h=sqrt(h); return vec2(-b-h,-b+h); }
void mainImage(out vec4 fragColor, vec2 fc){
  vec2 uv=(fc-.5*iResolution.xy)/iResolution.y;
  vec3 ro=vec3(0.,.7,-6.); vec3 ta=vec3(.7,0.,0.);
  vec3 ww=normalize(ta-ro), uu=normalize(cross(ww,vec3(0,1,0))), vv=cross(uu,ww);
  vec3 rd=normalize(uv.x*uu+uv.y*vv+1.7*ww);
  vec3 L=normalize(vec3(-1.,.35,-.25));
  // background: nebula + stars
  vec2 sp=uv*3.;
  vec3 col=vec3(.01,.01,.03);
  float neb=fbm(sp*1.2+fbm(sp*2.+iTime*.02)*1.5);
  col+=mix(vec3(.35,.08,.45),vec3(.05,.3,.55),fbm(sp*.8+7.))*pow(neb,3.)*1.6;
  vec2 st=fc*.6; float s=hash(floor(st)); col+=step(.997,s)*vec3(1.)*(.5+.5*sin(iTime*3.+s*100.));
  float tilt=.42; vec3 rn=normalize(vec3(0.,cos(tilt),sin(tilt)));
  vec2 hp=sph(ro,rd,1.);
  // rings (plane through origin)
  float tr=-dot(ro,rn)/dot(rd,rn);
  vec3 rp=ro+rd*tr; float rr=length(rp);
  float ringA=0.; vec3 ringC=vec3(0.);
  if(tr>0.&&rr>1.35&&rr<2.4){
    float band=.55+.45*sin(rr*38.)*sin(rr*11.+1.)+ (noise(vec2(rr*80.,0.))-.5)*.6;
    ringA=clamp(band,0.,1.)*smoothstep(1.35,1.45,rr)*smoothstep(2.4,2.2,rr)*.85;
    ringC=mix(vec3(.95,.8,.6),vec3(.7,.6,.55),noise(vec2(rr*20.,1.)));
    // planet shadow on ring
    vec2 sh=sph(rp,L,1.); float lit=sh.x>0.?.08:1.;
    ringC*=lit*(.5+.6*abs(dot(rn,L))+.3);
  }
  bool ringFront = ringA>0. && (hp.x<0. || tr<hp.x);
  if(hp.x>0.){
    vec3 p=ro+rd*hp.x; vec3 n=p;
    float lat=asin(n.y*cos(tilt)-n.z*sin(tilt));
    float bands=fbm(vec2(lat*14.+fbm(vec2(lat*20.,atan(n.x,n.z)*2.+iTime*.05))*1.2,0.5));
    vec3 alb=mix(vec3(.75,.38,.2),vec3(.95,.8,.6),bands); alb=mix(alb,vec3(.6,.35,.25),smoothstep(.6,.8,bands)*.6);
    float dif=clamp(dot(n,L),0.,1.);
    // ring shadow on planet
    float t2=-dot(p,rn)/dot(L,rn); vec3 q=p+L*t2; float qr=length(q);
    float rs = (t2>0.&&qr>1.35&&qr<2.4)? .35 : 1.;
    vec3 pc=alb*dif*rs*1.05 + alb*.02;
    pc+=vec3(.4,.6,1.)*pow(1.-clamp(dot(-rd,n),0.,1.),3.)*.6*clamp(dot(n,L)+.3,0.,1.);
    col=pc;
  }
  // atmosphere glow
  float d=length(cross(rd,-ro)); col+=vec3(.3,.5,1.)*exp(-max(d-1.,0.)*18.)*.35*smoothstep(-.2,.6,dot(normalize(ro+rd*dot(-ro,rd)),L));
  if(ringA>0.&&(ringFront||hp.x<0.)) col=mix(col,ringC,ringA);
  fragColor=vec4(post(col*1.15,fc),1.);
}
