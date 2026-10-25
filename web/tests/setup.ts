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

// vitest khong bat globals -> RTL khong tu cleanup; tu dong go DOM sau moi test (chi o jsdom).
if (typeof document !== "undefined") {
  const { afterEach } = await import("vitest");
  const { cleanup } = await import("@testing-library/react");
  afterEach(() => cleanup());
}
