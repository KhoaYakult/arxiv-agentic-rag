"use client";
import { useEffect, useState } from "react";

function useMediaQuery(query: string): boolean {
  const [matches, setMatches] = useState(false);
  useEffect(() => {
    const mq = window.matchMedia(query);
    const update = () => setMatches(mq.matches);
    update();
    mq.addEventListener("change", update);
    return () => mq.removeEventListener("change", update);
  }, [query]);
  return matches;
}

export function useIsMobile(): boolean {
  return useMediaQuery("(max-width: 767px)");
}

// Duoi 1024px khung chat (min 420px) + panel PDF 45% khong vua nhau: PDF mo toan man hinh.
export function useIsNarrow(): boolean {
  return useMediaQuery("(max-width: 1023px)");
}
