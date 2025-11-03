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

//MODAL STUFF//

document.addEventListener("DOMContentLoaded", () => {
  // OPEN MODAL for org-logo and usc-icon
  document.querySelectorAll(".org-logo, .usc-icon").forEach((trigger) => {
    trigger.addEventListener("click", (e) => {
      e.preventDefault();
      const modalId = trigger.getAttribute("data-modal");
      const modal = document.getElementById(modalId);
      if (modal) {
        document.body.appendChild(modal);
        modal.classList.add("visible");
        document.body.style.overflow = "hidden";
      }
    });
  });

  // CLOSE MODAL (X)
  document.querySelectorAll(".modal .close").forEach((btn) => {
    btn.addEventListener("click", () => {
      const modal = btn.closest(".modal");
      if (modal) {
        modal.classList.remove("visible");
        document.body.style.overflow = "";
      }
    });
  });

  // CLOSE MODAL when clicking outside content
  document.addEventListener("click", (e) => {
    const modal = document.querySelector(".modal.visible");
    if (modal && e.target === modal) {
      modal.classList.remove("visible");
      document.body.style.overflow = "";
    }
  });

  // CLOSE MODAL on Escape
  window.addEventListener("keydown", (e) => {
    if (e.key === "Escape") {
      document.querySelectorAll(".modal.visible").forEach((m) => {
        m.classList.remove("visible");
        document.body.style.overflow = "";
      });
    }
  });
});

//dont touch above this//

document.addEventListener("DOMContentLoaded", () => {
  // === OPEN BUBBLE MODAL ===
  document.querySelectorAll(".usc-icon, .bubble-trigger").forEach((trigger) => {
    trigger.addEventListener("click", (e) => {
      e.preventDefault();
      const modalId = trigger.getAttribute("data-modal");
      const modal = document.getElementById(modalId);

      if (modal) {
        document.body.appendChild(modal);
        modal.classList.add("visible");

        // ✅ Keep background scroll enabled
        document.body.style.overflow = "auto";
      }
    });
  });

  // === CLOSE BUTTON ===
  document.querySelectorAll(".modal-bubble .close").forEach((btn) => {
    btn.addEventListener("click", () => {
      const modal = btn.closest(".modal-bubble");
      if (modal) {
        modal.classList.remove("visible");
      }
    });
  });

  // === CLICK OUTSIDE TO CLOSE ===
  document.addEventListener("click", (e) => {
    const openModal = document.querySelector(".modal-bubble.visible");
    if (openModal && e.target === openModal) {
      openModal.classList.remove("visible");
    }
  });

  // === ESC KEY CLOSE ===
  window.addEventListener("keydown", (e) => {
    if (e.key === "Escape") {
      document.querySelectorAll(".modal-bubble.visible").forEach((m) => {
        m.classList.remove("visible");
      });
    }
  });
});



