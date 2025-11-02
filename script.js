// ===============================
// FADE-IN ANIMATIONS
// ===============================
document.addEventListener("DOMContentLoaded", () => {
  const fadeElements = document.querySelectorAll(".fade-in, .reveal");

  // Immediately show any element already visible
  fadeElements.forEach((el) => {
    const rect = el.getBoundingClientRect();
    if (rect.top < window.innerHeight * 0.9) {
      el.classList.add("visible");
    }
  });

  // Observe the rest
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
// CAROUSEL LOGIC
// ===============================
document.addEventListener("DOMContentLoaded", () => {
  document.querySelectorAll(".carousel-container").forEach((carousel) => {
    const slides = carousel.querySelectorAll(".slide");
    const next = carousel.querySelector(".next");
    const prev = carousel.querySelector(".prev");
    const dotsContainer = carousel.querySelector(".carousel-dots");
    let index = 0;

    // Create dots dynamically
    if (dotsContainer) {
      dotsContainer.innerHTML = "";
      slides.forEach((_, i) => {
        const dot = document.createElement("button");
        dot.addEventListener("click", () => showSlide(i));
        dotsContainer.appendChild(dot);
      });
    }

    const dots = dotsContainer ? dotsContainer.querySelectorAll("button") : [];

    function showSlide(i) {
      slides.forEach((s) => s.classList.remove("active"));
      dots.forEach((d) => d.classList.remove("active"));
      slides[i].classList.add("active");
      if (dots[i]) dots[i].classList.add("active");
      index = i;
    }

    if (next)
      next.addEventListener("click", () => {
        index = (index + 1) % slides.length;
        showSlide(index);
      });

    if (prev)
      prev.addEventListener("click", () => {
        index = (index - 1 + slides.length) % slides.length;
        showSlide(index);
      });

    setInterval(() => {
      index = (index + 1) % slides.length;
      showSlide(index);
    }, 7000);

    showSlide(index);
  });
});

// ===============================
// Scroll-triggered fade-in
// ===============================
document.addEventListener("DOMContentLoaded", () => {
  const fadeElements = document.querySelectorAll(".fade-in, .reveal");

  fadeElements.forEach((el) => {
    const rect = el.getBoundingClientRect();
    if (rect.top < window.innerHeight * 0.9) el.classList.add("visible");
  });

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

document.addEventListener("DOMContentLoaded", () => {
  // open modal
  document.querySelectorAll(".org-logo").forEach((logo) => {
    logo.addEventListener("click", (e) => {
      e.preventDefault();
      const modalId = logo.getAttribute("data-modal");
      const modal = document.getElementById(modalId);

      if (modal) {
        // move modal to body to escape stacking contexts
        document.body.appendChild(modal);
        modal.classList.add("visible");
      }
    });
  });

  // close when clicking X
  document.querySelectorAll(".close").forEach((btn) => {
    btn.addEventListener("click", () => {
      btn.closest(".modal").classList.remove("visible");
    });
  });

  // close when clicking outside modal-content
  document.addEventListener("click", (e) => {
    const modal = document.querySelector(".modal.visible");
    if (modal && e.target === modal) {
      modal.classList.remove("visible");
    }
  });

  // close with Escape key
  window.addEventListener("keydown", (e) => {
    if (e.key === "Escape") {
      document.querySelectorAll(".modal.visible").forEach((m) =>
        m.classList.remove("visible")
      );
    }
  });
});

