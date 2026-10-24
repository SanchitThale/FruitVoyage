document.addEventListener("DOMContentLoaded", () => {
    const nodes = document.querySelectorAll(".reveal");

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
            {
                threshold: 0.12
            }
        );

        nodes.forEach((node, index) => {
            node.style.transitionDelay =
                `${(index % 3) * 90}ms`;

            observer.observe(node);
        });
    } else {
        nodes.forEach((node) => {
            node.classList.add("visible");
        });
    }

    // Automatically hide success/error notifications.
    document.querySelectorAll(".flash").forEach((message) => {
        window.setTimeout(() => {
            message.style.opacity = "0";
            message.style.transform = "translateX(18px)";

            window.setTimeout(() => {
                message.remove();
            }, 350);
        }, 3500);
    });
});