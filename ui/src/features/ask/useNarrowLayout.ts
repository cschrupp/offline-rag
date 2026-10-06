import { useEffect, useState } from "react";

/** Matches `.knowledge-layout` responsive breakpoint in global.css. */
export const NARROW_LAYOUT_MEDIA = "(max-width: 960px)";

export function useNarrowLayout(): boolean {
  const [narrow, setNarrow] = useState(() => {
    if (typeof window === "undefined" || typeof window.matchMedia !== "function") {
      return false;
    }
    return window.matchMedia(NARROW_LAYOUT_MEDIA).matches;
  });

  useEffect(() => {
    if (typeof window.matchMedia !== "function") return;
    const media = window.matchMedia(NARROW_LAYOUT_MEDIA);
    const onChange = () => setNarrow(media.matches);
    onChange();
    media.addEventListener("change", onChange);
    return () => media.removeEventListener("change", onChange);
  }, []);

  return narrow;
}
