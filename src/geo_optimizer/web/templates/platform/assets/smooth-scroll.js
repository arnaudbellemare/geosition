(function () {
  var reduceMotion = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  var coarsePointer = window.matchMedia && window.matchMedia('(pointer: coarse)').matches;
  var isPlatformApp = /^\/platform\/(?:dashboard|index|login|register|forgot-password|reset-password)/.test(
    window.location.pathname
  );

  if (reduceMotion || coarsePointer || isPlatformApp || !window.Lenis) {
    document.documentElement.classList.add('native-scroll');
    return;
  }

  var lenis = new window.Lenis({
    duration: 1.08,
    easing: function (t) {
      return Math.min(1, 1.001 - Math.pow(2, -10 * t));
    },
    smoothWheel: true,
    wheelMultiplier: 0.92,
    touchMultiplier: 1,
    autoResize: true,
  });

  function raf(time) {
    lenis.raf(time);
    window.requestAnimationFrame(raf);
  }

  window.requestAnimationFrame(raf);
  window.GEOSITION_LENIS = lenis;

  document.addEventListener('visibilitychange', function () {
    if (document.hidden) {
      lenis.stop();
    } else {
      lenis.start();
      lenis.resize();
    }
  });

  window.addEventListener('pageshow', function () {
    lenis.resize();
  });
})();
