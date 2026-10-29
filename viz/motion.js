/* Scroll reveal, shared by every page.

   Blocks fade up as they enter the viewport, and blocks that arrive together
   are staggered slightly so the eye reads them in order. Diagrams marked
   .wipe draw left to right, the direction data flows through the pipeline.

   Nothing is hidden unless this script is running and the viewer has not asked
   for reduced motion: the hiding CSS only applies under html.motion, which is
   set here. Each revealed element receives a "revealed" event, so a page can
   start its own animation (a count-up, say) at the moment it comes into view. */
(function(){
  const reduce = window.matchMedia && matchMedia("(prefers-reduced-motion: reduce)").matches;
  if (reduce || !("IntersectionObserver" in window)) return;
  document.documentElement.classList.add("motion");

  const TARGETS = [
    ".sec-h", ".wrap > .card", ".main .card", ".foot",            // control room
    ".prose > section > *:not(.ideas)", ".idea",                  // documentation
    ".faq .prose > *", ".faq footer",                             // FAQ
  ].join(",");

  function show(el, delay){
    el.style.setProperty("--d", delay + "ms");
    el.classList.add("in");
    el.dispatchEvent(new CustomEvent("revealed"));
  }

  document.addEventListener("DOMContentLoaded", () => {
    const io = new IntersectionObserver(entries => {
      let n = 0;
      entries.forEach(e => {
        // Anything already above the viewport (a jump to an anchor, say) is
        // shown at once, or scrolling back up would find it still hidden.
        if (e.isIntersecting || e.boundingClientRect.bottom < 0){
          show(e.target, e.isIntersecting ? Math.min(n++ * 70, 280) : 0);
          io.unobserve(e.target);
        }
      });
    }, {rootMargin:"0px 0px -6% 0px"});

    document.querySelectorAll(TARGETS).forEach(el => {
      el.classList.add("reveal");
      io.observe(el);
    });
  });
})();
