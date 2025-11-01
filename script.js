// ===============================
// Scroll-triggered reveal animation (no blank flash)
// ===============================
document.addEventListener("DOMContentLoaded", () => {
  const fadeElements = document.querySelectorAll(".fade-in, .reveal");

  // Immediately show elements that are already in view on load
  fadeElements.forEach((el) => {
    const rect = el.getBoundingClientRect();
    if (rect.top < window.innerHeight * 0.9) {
      el.classList.add("visible");
    }
  });

  // Observe scroll for rest of elements
  const observer = new IntersectionObserver(
    (entries) => {
      entries.forEach((entry) => {
        if (entry.isIntersecting) {
          entry.target.classList.add("visible");
          observer.unobserve(entry.target);
        }
      });
    },
    { threshold: 0.2 }
  );

  fadeElements.forEach((el) => observer.observe(el));
});


// ===============================
// Multi-carousel support (unchanged)
// ===============================
document.addEventListener("DOMContentLoaded", () => {
  const carousels = document.querySelectorAll(".carousel-container");

  carousels.forEach((carouselContainer) => {
    const slides = carouselContainer.querySelectorAll(".slide");
    const next = carouselContainer.querySelector(".next");
    const prev = carouselContainer.querySelector(".prev");
    const dotsContainer = carouselContainer.querySelector(".carousel-dots");
    let index = 0;

    // === Create dots dynamically ===
    dotsContainer.innerHTML = "";
    slides.forEach((_, i) => {
      const dot = document.createElement("button");
      dot.addEventListener("click", () => {
        index = i;
        showSlide(index);
      });
      dotsContainer.appendChild(dot);
    });

    const dots = dotsContainer.querySelectorAll("button");

    // === Show selected slide ===
    function showSlide(i) {
      slides.forEach((s) => s.classList.remove("active"));
      dots.forEach((d) => d.classList.remove("active"));
      slides[i].classList.add("active");
      dots[i].classList.add("active");
    }

    // === Button navigation ===
    next.addEventListener("click", () => {
      index = (index + 1) % slides.length;
      showSlide(index);
    });

    prev.addEventListener("click", () => {
      index = (index - 1 + slides.length) % slides.length;
      showSlide(index);
    });

    // === Auto-advance every 7s ===
    setInterval(() => {
      index = (index + 1) % slides.length;
      showSlide(index);
    }, 7000);

    // === Initialize ===
    showSlide(index);
  });
});
