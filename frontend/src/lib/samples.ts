// Showcase media in /public/samples. These are original procedural renders made for this app
// (no third-party licensing), used as illustrative examples and prompt ideas, not as model outputs.
// Swap them for real generations whenever you like: keep the same shape.

export type Sample = {
  id: string;
  title: string;
  media: "image" | "video";
  src: string; // image, or video poster
  video?: string;
  prompt: string;
  aspect: "16/9" | "1/1" | "4/5";
  tag: string;
};

export const SAMPLES: Sample[] = [
  {
    id: "aurora",
    title: "Northern lights",
    media: "video",
    src: "/samples/aurora-loop.jpg",
    video: "/samples/aurora-loop.mp4",
    prompt:
      "Slow cinematic shot of green and violet aurora rippling above a still mountain lake at night, stars, reflections, ambient wind sound",
    aspect: "16/9",
    tag: "Text to video",
  },
  {
    id: "orbs",
    title: "Pastel product set",
    media: "image",
    src: "/samples/orbs.jpg",
    video: "/samples/orbs-loop.mp4",
    prompt: "Glossy pastel spheres and a golden torus on a seamless peach studio backdrop, soft key light, gentle shadows, product photography",
    aspect: "1/1",
    tag: "Text to image",
  },
  {
    id: "alpine",
    title: "Alpine flyover",
    media: "video",
    src: "/samples/alpine-loop.jpg",
    video: "/samples/alpine-loop.mp4",
    prompt: "Drone flyover of a green alpine valley at golden hour, snow-capped peaks on the horizon, light haze, smooth forward motion",
    aspect: "16/9",
    tag: "Text to video",
  },
  {
    id: "silk",
    title: "Liquid silk",
    media: "image",
    src: "/samples/silk.jpg",
    video: "/samples/silk-loop.mp4",
    prompt: "Abstract flowing silk in coral, indigo and amber, soft sheen, macro, editorial background",
    aspect: "4/5",
    tag: "Text to image",
  },
  {
    id: "dunes",
    title: "Desert dunes",
    media: "image",
    src: "/samples/dunes.jpg",
    prompt: "Wide shot of rolling sand dunes with wind ripples, late afternoon sun, long shadows, clear blue sky",
    aspect: "16/9",
    tag: "Text to image",
  },
  {
    id: "planet",
    title: "Ringed planet",
    media: "image",
    src: "/samples/planet.jpg",
    prompt: "A banded gas giant with wide icy rings against a violet nebula, cinematic sci-fi matte painting",
    aspect: "16/9",
    tag: "Text to image",
  },
];
