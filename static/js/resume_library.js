document.querySelectorAll("[data-file-dropzone]").forEach((dropzone) => {
    const input = dropzone.querySelector('input[type="file"]');
    const fileName = dropzone.querySelector("[data-file-name]");
    if (!input || !fileName) return;

    const updateFileName = () => {
        const files = Array.from(input.files || []);
        if (!files.length) {
            fileName.textContent = "Drop resumes here";
        } else if (files.length === 1) {
            fileName.textContent = files[0].name;
        } else {
            fileName.textContent = `${files.length} resumes selected`;
        }
    };

    input.addEventListener("change", updateFileName);

    ["dragenter", "dragover"].forEach((eventName) => {
        dropzone.addEventListener(eventName, (event) => {
            event.preventDefault();
            dropzone.classList.add("is-dragging");
        });
    });

    ["dragleave", "drop"].forEach((eventName) => {
        dropzone.addEventListener(eventName, (event) => {
            event.preventDefault();
            dropzone.classList.remove("is-dragging");
        });
    });

    dropzone.addEventListener("drop", (event) => {
        const files = event.dataTransfer.files;
        if (files.length) {
            input.files = files;
            updateFileName();
        }
    });
});
