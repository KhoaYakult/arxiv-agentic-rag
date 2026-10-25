import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  /* config options here */
  turbopack: {
    // Safari/iOS < 18 khong co URL.parse / Promise.withResolvers (build hien dai cua pdf.js can chung)
    // -> react-pdf phai nap build "legacy". Alias khop nguyen ten module "pdfjs-dist" (import thuan cua react-pdf).
    resolveAlias: {
      "pdfjs-dist": "pdfjs-dist/legacy/build/pdf.mjs",
    },
    rules: {
      "*.css": {
        loaders: ["@tailwindcss/turbopack"],
        as: "*.css",
      },
    },
  },
};

export default nextConfig;
