import type { MetadataRoute } from "next";

export default function manifest(): MetadataRoute.Manifest {
  return {
    name: "AgriAI",
    short_name: "AgriAI",
    description: "आपके खेत का अपना खेती-सलाहकार",
    start_url: "/",
    display: "standalone",
    background_color: "#fafaf9",
    theme_color: "#166534",
    lang: "hi",
    icons: [
      { src: "/icon-192.png", sizes: "192x192", type: "image/png" },
      { src: "/icon-512.png", sizes: "512x512", type: "image/png" },
    ],
  };
}
