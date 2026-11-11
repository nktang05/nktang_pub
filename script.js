// ===============================
// SITE INIT
// ===============================
document.addEventListener("DOMContentLoaded", () => {
  const fadeElements = document.querySelectorAll(".fade-in, .reveal");

  const revealVisible = () => {
    fadeElements.forEach((el) => {
      const rect = el.getBoundingClientRect();
      if (rect.top < window.innerHeight * 0.9) {
        el.classList.add("visible");
      }
    });
  };

  revealVisible();

  if ("IntersectionObserver" in window) {
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
  }

  // ===============================
  // CAROUSEL LOGIC
  // ===============================
  document.querySelectorAll(".carousel-container").forEach((carousel) => {
    const slides = carousel.querySelectorAll(".slide");
    if (!slides.length) return;

    const next = carousel.querySelector(".next");
    const prev = carousel.querySelector(".prev");
    const dotsContainer = carousel.querySelector(".carousel-dots");
    let index = 0;

    if (dotsContainer) {
      dotsContainer.innerHTML = "";
      slides.forEach((_, i) => {
        const dot = document.createElement("button");
        dot.type = "button";
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

    if (next) {
      next.addEventListener("click", () => {
        index = (index + 1) % slides.length;
        showSlide(index);
      });
    }

    if (prev) {
      prev.addEventListener("click", () => {
        index = (index - 1 + slides.length) % slides.length;
        showSlide(index);
      });
    }

    const intervalId = setInterval(() => {
      index = (index + 1) % slides.length;
      showSlide(index);
    }, 7000);

    carousel.dataset.intervalId = String(intervalId);
    showSlide(index);
  });

  // ===============================
  // MODAL LOGIC
  // ===============================
  const lockBodyScroll = (shouldLock) => {
    document.body.classList.toggle("modal-open", shouldLock);
  };

  const closeVisibleModal = (selector) => {
    document.querySelectorAll(selector).forEach((modal) => {
      modal.classList.remove("visible");
    });
  };

  document.querySelectorAll(".org-logo, .usc-icon, .bubble-trigger").forEach((trigger) => {
    trigger.addEventListener("click", (e) => {
      e.preventDefault();
      const modalId = trigger.getAttribute("data-modal");
      const modal = document.getElementById(modalId);
      if (!modal) return;

      document.body.appendChild(modal);
      modal.classList.add("visible");
      lockBodyScroll(true);
    });
  });

  document.querySelectorAll(".modal .close, .modal-bubble .close").forEach((btn) => {
    btn.addEventListener("click", () => {
      const modal = btn.closest(".modal, .modal-bubble");
      if (modal) {
        modal.classList.remove("visible");
      }

      const noVisibleModal = !document.querySelector(".modal.visible, .modal-bubble.visible");
      if (noVisibleModal) lockBodyScroll(false);
    });
  });

  document.addEventListener("click", (e) => {
    const modal = document.querySelector(".modal.visible");
    if (modal && e.target === modal) {
      modal.classList.remove("visible");
    }

    const bubble = document.querySelector(".modal-bubble.visible");
    if (bubble && e.target === bubble) {
      bubble.classList.remove("visible");
    }

    if (!document.querySelector(".modal.visible, .modal-bubble.visible")) {
      lockBodyScroll(false);
    }
  });

  window.addEventListener("keydown", (e) => {
    if (e.key !== "Escape") return;

    closeVisibleModal(".modal.visible");
    closeVisibleModal(".modal-bubble.visible");

    const hasVisibleModal = document.querySelector(".modal.visible, .modal-bubble.visible");
    if (!hasVisibleModal) lockBodyScroll(false);
  });
});


