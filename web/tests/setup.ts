// web/tests/setup.ts
import "@testing-library/jest-dom/vitest";

// jsdom khong co matchMedia (useIsMobile dung no) -> gia lap "desktop".
if (typeof window !== "undefined" && !window.matchMedia) {
  window.matchMedia = (query: string) =>
    ({
      matches: false, media: query, onchange: null,
      addEventListener: () => {}, removeEventListener: () => {},
      addListener: () => {}, removeListener: () => {}, dispatchEvent: () => false,
    }) as MediaQueryList;
}
