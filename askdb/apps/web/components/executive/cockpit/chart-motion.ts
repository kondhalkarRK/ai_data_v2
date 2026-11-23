/** Short, non-looping reveals. No transforms that can distort the chart geometry. */
export function animateChart(body: HTMLElement): () => void {
  const media = window.matchMedia("(prefers-reduced-motion: reduce)");
  if (media.matches) return () => {};
  let played = false;
  const animations: Animation[] = [];
  const finish = () => animations.forEach(animation => { try { animation.finish(); } catch { animation.cancel(); } });
  const play = () => {
    if (played) return;
    const marks = body.querySelectorAll<HTMLElement | SVGElement>("[data-chart-grow], [data-chart-line], [data-chart-reveal]");
    if (!marks.length) return;
    played = true;
    observer.disconnect();
    marks.forEach((mark, index) => {
      if (!mark.animate) return;
      const horizontal = mark.hasAttribute("data-chart-grow") || mark.hasAttribute("data-chart-line");
      animations.push(mark.animate(horizontal
        ? [{ clipPath: "inset(0 100% 0 0)" }, { clipPath: "inset(0 0 0 0)" }]
        : [{ opacity: 0.25 }, { opacity: 1 }], {
        duration: horizontal ? 650 : 450, delay: Math.min(index * 20, 160), easing: "cubic-bezier(.22,1,.36,1)",
      }));
    });
  };
  // SVGs mount after their ResizeObserver obtains a width. Do not replay on hover.
  const observer = new MutationObserver(play);
  observer.observe(body, { childList: true, subtree: true });
  play();
  const onReducedMotion = () => { if (media.matches) { observer.disconnect(); finish(); } };
  media.addEventListener("change", onReducedMotion);
  window.addEventListener("beforeprint", finish);
  return () => { observer.disconnect(); animations.forEach(animation => animation.cancel()); media.removeEventListener("change", onReducedMotion); window.removeEventListener("beforeprint", finish); };
}
