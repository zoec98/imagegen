document.addEventListener('DOMContentLoaded', () => {
    initAutoSubmit();
    initLoadingStates();
    initConfirmations();
    initThemeToggle();
    initImageUpload();
});

function initThemeToggle() {
    const toggleBtn = document.getElementById('theme-toggle');

    // Check local storage or system preference
    const savedTheme = localStorage.getItem('theme');
    const prefersLight = window.matchMedia('(prefers-color-scheme: light)').matches;

    if (savedTheme === 'light' || (!savedTheme && prefersLight)) {
        document.body.classList.add('light-theme');
    }

    toggleBtn.addEventListener('click', () => {
        document.body.classList.toggle('light-theme');
        const isLight = document.body.classList.contains('light-theme');
        localStorage.setItem('theme', isLight ? 'light' : 'dark');
    });
}

/**
 * Automatically submits the form when specific inputs change.
 * Replaces inline onchange="this.form.submit()"
 */
function initAutoSubmit() {
    const autoSubmitInputs = [
        'gallery-width',
        'gallery-height',
        'model-name'
    ];

    autoSubmitInputs.forEach(id => {
        const element = document.getElementById(id);
        if (element) {
            element.addEventListener('change', (e) => {
                e.target.form.submit();
            });
        }
    });

    // Specific handling for the style dropdown which had inline logic
    const styleInput = document.getElementById('style-name');
    if (styleInput) {
        styleInput.addEventListener('change', () => {
            // The original logic clicked a hidden button to trigger a specific action
            const appendBtn = document.getElementById('append-style-button');
            if (appendBtn) appendBtn.click();
        });
    }
}

/**
 * Adds loading states to buttons to provide visual feedback.
 */
function initLoadingStates() {
    const mainForm = document.getElementById('main-form');
    if (!mainForm) return;

    mainForm.addEventListener('submit', (e) => {
        // Find the button that triggered the submit
        // Note: 'submitter' is a modern property of the submit event
        const submitter = e.submitter;

        // Only show loading for the "Run" action as it takes time
        if (submitter && submitter.value === 'run') {
            const originalText = submitter.innerHTML;
            const originalWidth = submitter.offsetWidth; // Keep width fixed

            submitter.style.width = `${originalWidth}px`;
            submitter.innerHTML = '<span>Generating...</span> <span class="spinner"></span>';
            submitter.classList.add('loading');

            // We don't disable immediately to allow the form data to send, 
            // but in a real SPA we would. Here let it submit.
            // Re-enabling happens automatically when page reloads.
        }
    });
}

/**
 * Handles confirmation dialogs cleanly.
 * Replaces inline onclick="return confirm(...)"
 */
function initConfirmations() {
    const dangerousButtons = document.querySelectorAll('button.danger');

    dangerousButtons.forEach(btn => {
        btn.addEventListener('click', (e) => {
            const message = btn.getAttribute('data-confirm') || 'Are you sure you want to proceed?';
            if (!confirm(message)) {
                e.preventDefault();
            }
        });
    });
}

/**
 * Handles local image upload and URL insertion.
 */
function initImageUpload() {
    const uploadBtn = document.getElementById('upload-image-btn');
    const fileInput = document.getElementById('local-image-upload');
    const urlsTextarea = document.getElementById('image-urls');

    if (!uploadBtn || !fileInput || !urlsTextarea) return;

    uploadBtn.addEventListener('click', () => {
        fileInput.click();
    });

    fileInput.addEventListener('change', async () => {
        if (!fileInput.files || fileInput.files.length === 0) return;

        const file = fileInput.files[0];
        const formData = new FormData();
        formData.append('file', file);

        // UI Feedback
        const originalText = uploadBtn.textContent;
        uploadBtn.textContent = 'Uploading...';
        uploadBtn.disabled = true;

        try {
            const response = await fetch('/api/upload', {
                method: 'POST',
                body: formData
            });

            if (!response.ok) {
                const errorData = await response.json();
                throw new Error(errorData.error || 'Upload failed');
            }

            const data = await response.json();
            const url = data.url;

            // Append URL to textarea
            const currentVal = urlsTextarea.value.trim();
            if (currentVal) {
                urlsTextarea.value = currentVal + '\n' + url;
            } else {
                urlsTextarea.value = url;
            }

        } catch (err) {
            console.error('Upload error:', err);
            alert('Failed to upload image: ' + err.message);
        } finally {
            // Reset UI
            uploadBtn.textContent = originalText;
            uploadBtn.disabled = false;
            fileInput.value = ''; // Allow re-uploading same file
        }
    });
}
