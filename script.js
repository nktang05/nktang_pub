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

// ===============================
// Modal Logic
// ===============================
let activeModal = null;

function openModal(id) {
  if (activeModal) {
    activeModal.classList.remove("visible");
    setTimeout(() => (activeModal.style.display = "none"), 200);
    activeModal = null;
  }

  const modal = document.getElementById(`modal-${id}`);
  if (modal) {
    modal.style.display = "flex";
    requestAnimationFrame(() => modal.classList.add("visible"));
    activeModal = modal;
    document.body.style.overflow = "hidden";
  }
}

function closeModal(id) {
  const modal = document.getElementById(`modal-${id}`);
  if (modal) {
    modal.classList.remove("visible");
    setTimeout(() => {
      modal.style.display = "none";
      document.body.style.overflow = "";
      if (activeModal === modal) activeModal = null;
    }, 200);
  }
}

window.addEventListener("click", (e) => {
  if (activeModal && e.target === activeModal)
    closeModal(activeModal.id.replace("modal-", ""));
});

window.addEventListener("keydown", (e) => {
  if (e.key === "Escape" && activeModal)
    closeModal(activeModal.id.replace("modal-", ""));
});

window.openModal = openModal;
window.closeModal = closeModal;
