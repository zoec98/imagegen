document.addEventListener('DOMContentLoaded', () => {
    initAutoSubmit();
    initLoadingStates();
    initConfirmations();
    initThemeToggle();
    initModelSizeSync();
    initDualInputs();
    initPromptAutoLoad();
    initImageUpload();
    initStyleControls();
    initImageSourceControls();
    initPromptControls();
});

/**
 * Initializes style modifier specific logic:
 * - Loading text on select
 * - Inserting text into prompt
 * - Saving new styles
 */
function initStyleControls() {
    const styleSelect = document.getElementById('style-name-preset');
    const styleTextarea = document.getElementById('style-name-custom');
    const insertBtn = document.getElementById('insert-style-btn');
    const saveStyleBtn = document.getElementById('save-style-btn');
    const promptTextarea = document.getElementById('prompt-text');

    if (!styleSelect || !styleTextarea) return;

    // 1. Fetch content on selection
    styleSelect.addEventListener('change', async () => {
        const name = styleSelect.value;
        if (!name) {
            // Optional: Should we clear it? User didn't specify. 
            // "replacing text if there already was some" -> implies overwrite.
            // If "Custom" (empty value) is selected, maybe leave as is or clear?
            // Let's clear if empty value is selected to be clean.
            styleTextarea.value = '';
            return;
        }

        try {
            const response = await fetch(`/api/style/${encodeURIComponent(name)}`);
            if (response.ok) {
                const data = await response.json();
                styleTextarea.value = data.text || '';
            }
        } catch (err) {
            console.error('Failed to load style:', err);
        }
    });

    // 2. Insert Button
    if (insertBtn && promptTextarea) {
        insertBtn.addEventListener('click', () => {
            const textToInsert = styleTextarea.value.trim();
            if (!textToInsert) return;

            const currentPrompt = promptTextarea.value;
            if (currentPrompt) {
                promptTextarea.value = textToInsert + '\n' + currentPrompt;
            } else {
                promptTextarea.value = textToInsert;
            }
        });
    }

    // 3. Save Style Button
    if (saveStyleBtn) {
        const modal = document.getElementById('save-style-modal');
        const confirmBtn = document.getElementById('confirm-save-style-btn');
        const cancelBtn = document.getElementById('cancel-style-btn');
        const nameInput = document.getElementById('new-style-name');

        const closeModal = () => {
            modal.classList.remove('active');
            nameInput.value = '';
        };

        const openModal = () => {
            const textToSave = styleTextarea.value.trim();
            if (!textToSave) {
                alert('Please enter some style text to save.');
                return;
            }

            // Pre-populate name if a preset is selected
            const currentName = styleSelect.value;
            if (currentName) {
                nameInput.value = currentName;
            }

            modal.classList.add('active');
            nameInput.focus();
        };

        saveStyleBtn.addEventListener('click', (e) => {
            e.preventDefault();
            openModal();
        });

        // Cancel / Close
        if (cancelBtn) {
            cancelBtn.addEventListener('click', closeModal);
        }

        // Close on click outside
        if (modal) {
            modal.addEventListener('click', (e) => {
                if (e.target === modal) closeModal();
            });
        }

        // Confirm Save
        if (confirmBtn) {
            confirmBtn.addEventListener('click', async () => {
                const name = nameInput.value.trim();
                const textToSave = styleTextarea.value.trim();

                if (!name) {
                    alert('Please enter a name.');
                    return;
                }

                try {
                    confirmBtn.disabled = true;
                    confirmBtn.textContent = 'Saving...';

                    const response = await fetch('/api/save-style', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ name: name, text: textToSave })
                    });

                    if (response.ok) {
                        const data = await response.json();
                        alert(`Style saved as "${data.saved_name}"`);
                        window.location.reload();
                    } else {
                        const errData = await response.json();
                        alert('Error saving style: ' + (errData.error || 'Unknown error'));
                    }
                } catch (err) {
                    console.error('Save failed:', err);
                    alert('Failed to save style.');
                } finally {
                    confirmBtn.disabled = false;
                    confirmBtn.textContent = 'Save';
                    closeModal();
                }
            });
        }
    }

    // 4. Delete Style Button
    const deleteBtn = document.getElementById('delete-style-btn');
    if (deleteBtn) {
        const modal = document.getElementById('delete-style-modal');
        const confirmBtn = document.getElementById('confirm-delete-style-btn');
        const cancelBtn = document.getElementById('cancel-delete-style-btn');
        const nameDisplay = document.getElementById('delete-style-name-display');

        const closeModal = () => {
            modal.classList.remove('active');
        };

        const openModal = () => {
            const name = styleSelect.value;
            if (!name) return; // Do nothing if no style selected

            nameDisplay.textContent = name;
            modal.classList.add('active');
        };

        deleteBtn.addEventListener('click', (e) => {
            e.preventDefault();
            openModal();
        });

        if (cancelBtn) cancelBtn.addEventListener('click', closeModal);
        if (modal) modal.addEventListener('click', (e) => { if (e.target === modal) closeModal(); });

        if (confirmBtn) {
            confirmBtn.addEventListener('click', async () => {
                const name = nameDisplay.textContent;
                try {
                    confirmBtn.disabled = true;
                    confirmBtn.textContent = 'Deleting...';

                    const response = await fetch('/api/delete-style', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ name: name })
                    });

                    if (response.ok) {
                        const data = await response.json();
                        alert(`Style "${data.deleted_name}" deleted.`);
                        window.location.reload();
                    } else {
                        const errData = await response.json();
                        alert('Error deleting style: ' + (errData.error || 'Unknown error'));
                    }
                } catch (err) {
                    console.error('Delete failed:', err);
                    alert('Failed to delete style.');
                } finally {
                    confirmBtn.disabled = false;
                    confirmBtn.textContent = 'Yes, Delete';
                    closeModal();
                }
            });
        }
    }
}

/**
 * Initializes prompt-specific logic:
 * - Loading text on select
 * - Saving new prompts
 * - Deleting existing prompts
 */
function initPromptControls() {
    const promptSelect = document.getElementById('prompt-name-preset');
    const promptTextarea = document.getElementById('prompt-text');
    const savePromptBtn = document.getElementById('save-prompt-btn');
    const deletePromptBtn = document.getElementById('delete-prompt-btn');

    if (!promptSelect || !promptTextarea) return;

    // 1. Fetch content on selection
    promptSelect.addEventListener('change', async () => {
        const name = promptSelect.value;
        if (!name) {
            // If "New / Custom" (empty value) is selected, maybe leave as is?
            // For prompts, let's NOT clear the main textarea because user might be typing a "New" prompt.
            return;
        }

        try {
            const response = await fetch(`/api/prompt/${encodeURIComponent(name)}`);
            if (response.ok) {
                const data = await response.json();
                promptTextarea.value = data.text || '';
            }
        } catch (err) {
            console.error('Failed to load prompt:', err);
        }
    });

    // 2. Save Prompt Button
    if (savePromptBtn) {
        const modal = document.getElementById('save-prompt-modal');
        const confirmBtn = document.getElementById('confirm-save-prompt-btn');
        const cancelBtn = document.getElementById('cancel-prompt-btn');
        const nameInput = document.getElementById('new-prompt-name');

        const closeModal = () => {
            modal.classList.remove('active');
            nameInput.value = '';
        };

        const openModal = () => {
            const textToSave = promptTextarea.value.trim();
            if (!textToSave) {
                alert('Please enter some prompt text to save.');
                return;
            }

            // Pre-populate name if a preset is selected
            const currentName = promptSelect.value;
            if (currentName) {
                nameInput.value = currentName;
            }

            modal.classList.add('active');
            nameInput.focus();
        };

        savePromptBtn.addEventListener('click', (e) => {
            e.preventDefault();
            openModal();
        });

        if (cancelBtn) cancelBtn.addEventListener('click', closeModal);
        if (modal) modal.addEventListener('click', (e) => { if (e.target === modal) closeModal(); });

        if (confirmBtn) {
            confirmBtn.addEventListener('click', async () => {
                const name = nameInput.value.trim();
                const textToSave = promptTextarea.value.trim();

                if (!name) {
                    alert('Please enter a name.');
                    return;
                }

                try {
                    confirmBtn.disabled = true;
                    confirmBtn.textContent = 'Saving...';

                    const response = await fetch('/api/save-prompt', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ name: name, text: textToSave })
                    });

                    if (response.ok) {
                        const data = await response.json();
                        alert(`Prompt saved as "${data.saved_name}"`);
                        window.location.reload();
                    } else {
                        const errData = await response.json();
                        alert('Error saving prompt: ' + (errData.error || 'Unknown error'));
                    }
                } catch (err) {
                    console.error('Save failed:', err);
                    alert('Failed to save prompt.');
                } finally {
                    confirmBtn.disabled = false;
                    confirmBtn.textContent = 'Save';
                    closeModal();
                }
            });
        }
    }

    // 3. Delete Prompt Button
    if (deletePromptBtn) {
        const modal = document.getElementById('delete-prompt-modal');
        const confirmBtn = document.getElementById('confirm-delete-prompt-btn');
        const cancelBtn = document.getElementById('cancel-delete-prompt-btn');
        const nameDisplay = document.getElementById('delete-prompt-name-display');

        const closeModal = () => {
            modal.classList.remove('active');
        };

        const openModal = () => {
            const name = promptSelect.value;
            if (!name) return; // Do nothing if no prompt selected

            nameDisplay.textContent = name;
            modal.classList.add('active');
        };

        deletePromptBtn.addEventListener('click', (e) => {
            e.preventDefault();
            openModal();
        });

        if (cancelBtn) cancelBtn.addEventListener('click', closeModal);
        if (modal) modal.addEventListener('click', (e) => { if (e.target === modal) closeModal(); });

        if (confirmBtn) {
            confirmBtn.addEventListener('click', async () => {
                const name = nameDisplay.textContent;
                try {
                    confirmBtn.disabled = true;
                    confirmBtn.textContent = 'Deleting...';

                    const response = await fetch('/api/delete-prompt', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ name: name })
                    });

                    if (response.ok) {
                        const data = await response.json();
                        alert(`Prompt "${data.deleted_name}" deleted.`);
                        window.location.reload();
                    } else {
                        const errData = await response.json();
                        alert('Error deleting prompt: ' + (errData.error || 'Unknown error'));
                    }
                } catch (err) {
                    console.error('Delete failed:', err);
                    alert('Failed to delete prompt.');
                } finally {
                    confirmBtn.disabled = false;
                    confirmBtn.textContent = 'Yes, Delete';
                    closeModal();
                }
            });
        }
    }

    // 4. Duplicate Prompt Button
    const duplicatePromptBtn = document.getElementById('duplicate-prompt-btn');
    if (duplicatePromptBtn) {
        duplicatePromptBtn.addEventListener('click', async (e) => {
            e.preventDefault();

            const name = promptSelect.value;
            const text = promptTextarea.value.trim();

            if (!name) {
                alert('Please select a prompt to duplicate.');
                return;
            }

            if (!text) {
                alert('No prompt text to duplicate.');
                return;
            }

            try {
                duplicatePromptBtn.disabled = true;
                duplicatePromptBtn.textContent = 'Duplicating...';

                const response = await fetch('/api/duplicate-prompt', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ name: name, text: text })
                });

                if (response.ok) {
                    const data = await response.json();
                    alert(`Prompt duplicated as "${data.duplicated_name}"`);
                    window.location.reload();
                } else {
                    const errData = await response.json();
                    alert('Error duplicating prompt: ' + (errData.error || 'Unknown error'));
                }
            } catch (err) {
                console.error('Duplicate failed:', err);
                alert('Failed to duplicate prompt.');
            } finally {
                duplicatePromptBtn.disabled = false;
                duplicatePromptBtn.textContent = 'Duplicate';
            }
        });
    }
}

function initImageSourceControls() {
    const toggleBtn = document.getElementById('toggle-image-preview');
    const inputContainer = document.getElementById('image-url-input-container');
    const previewContainer = document.getElementById('image-preview-container');
    const textarea = document.getElementById('image-urls');
    const uploadBtn = document.getElementById('upload-image-btn');
    const fileInput = document.getElementById('local-image-upload');

    if (!toggleBtn || !inputContainer || !previewContainer || !textarea) return;

    // Toggle Preview Mode
    toggleBtn.addEventListener('change', () => {
        if (toggleBtn.checked) {
            inputContainer.style.display = 'none';
            previewContainer.style.display = 'grid';
            renderImagePreviews(textarea.value, previewContainer);
        } else {
            inputContainer.style.display = 'block';
            previewContainer.style.display = 'none';
        }
    });

    // Upload Logic (Updated)
    if (uploadBtn && fileInput) {
        uploadBtn.addEventListener('click', () => fileInput.click());
        fileInput.addEventListener('change', async (e) => {
            const file = e.target.files[0];
            if (!file) return;

            const formData = new FormData();
            formData.append('file', file);

            try {
                uploadBtn.textContent = 'Uploading...';
                uploadBtn.disabled = true;

                const response = await fetch('/api/upload-image', {
                    method: 'POST',
                    body: formData
                });

                if (response.ok) {
                    const data = await response.json();
                    const newUrl = data.url;

                    // Append to textarea
                    const currentText = textarea.value.trim();
                    textarea.value = currentText ? `${currentText}\n${newUrl}` : newUrl;

                    // If in preview mode, refresh previews
                    if (toggleBtn.checked) {
                        renderImagePreviews(textarea.value, previewContainer);
                    }
                } else {
                    const err = await response.json();
                    alert('Upload failed: ' + (err.error || 'Unknown error'));
                }
            } catch (err) {
                console.error('Upload error:', err);
                alert('An error occurred during upload.');
            } finally {
                uploadBtn.textContent = 'Upload Local Image';
                uploadBtn.disabled = false;
                fileInput.value = ''; // Reset
            }
        });
    }
}

function renderImagePreviews(text, container) {
    container.innerHTML = '';
    const urls = text.split(/[\n,]+/).map(u => u.trim()).filter(u => u);

    if (urls.length === 0) {
        container.innerHTML = '<div style="grid-column: 1/-1; padding: 1rem; text-align: center; color: var(--text-secondary); font-size: 0.9rem;">No images added yet. Upload or switch to edit mode to paste URLs.</div>';
        return;
    }

    urls.forEach(url => {
        const item = document.createElement('div');
        item.className = 'image-preview-item';

        const img = document.createElement('img');
        img.src = url;
        img.title = url;

        img.onerror = () => {
            item.innerHTML = `
                <div class="image-preview-error">
                    <span>Broken Link<br>${url.substring(0, 20)}...</span>
                </div>
            `;
        };

        item.appendChild(img);
        container.appendChild(item);
    });
}


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
 * Initializes dual input groups (select + custom text) for mutual exclusion.
 */
function initDualInputs() {
    const groups = document.querySelectorAll('.dual-input-group');

    groups.forEach(group => {
        const select = group.querySelector('select');
        const input = group.querySelector('input');

        if (!select || !input) return;

        // Initial state
        if (input.value.trim()) {
            select.classList.add('disabled');
        }

        // Input handler
        input.addEventListener('input', () => {
            if (input.value.trim()) {
                select.classList.add('disabled');
            } else {
                select.classList.remove('disabled');
            }
        });

        // Select handler
        select.addEventListener('change', () => {
            // If user picks a preset, clear the custom input
            if (select.value) {
                input.value = '';
                select.classList.remove('disabled');
            }
        });
    });
}

/**
 * Updates the dimensions dropdown when the model selection changes.
 */
function initModelSizeSync() {
    const modelSelect = document.getElementById('model-name');
    const sizeSelect = document.getElementById('image-size-preset');

    if (!modelSelect || !sizeSelect) return;

    modelSelect.addEventListener('change', async () => {
        const model = modelSelect.value;
        if (!model) return;

        try {
            const response = await fetch(`/api/model-sizes/${encodeURIComponent(model)}`);
            if (!response.ok) return;

            const data = await response.json();
            const sizes = data.sizes || [];
            const defaultSize = data.default || '';
            const supportsUrls = data.supports_image_urls;

            // Toggle URL input visibility
            const urlsGroup = document.getElementById('image-urls-group');
            if (urlsGroup) {
                urlsGroup.style.display = supportsUrls ? 'block' : 'none';
            }

            // Clear existing options
            sizeSelect.innerHTML = '';

            // Add options
            sizes.forEach(size => {
                const option = document.createElement('option');
                option.value = size;
                option.textContent = size;
                if (size === defaultSize) {
                    option.selected = true;
                }
                sizeSelect.appendChild(option);
            });
            // Ensure default is selected
            sizeSelect.value = defaultSize;

        } catch (err) {
            console.error('Failed to fetch model sizes:', err);
        }
    });
}

/**
 * Automatically loads prompt text when a preset is selected.
 */
function initPromptAutoLoad() {
    const promptSelect = document.getElementById('prompt-name-preset');
    const promptText = document.getElementById('prompt-text');

    if (!promptSelect || !promptText) return;

    promptSelect.addEventListener('change', async () => {
        const name = promptSelect.value;
        if (!name) return; // Do not clear on 'New/Custom' to allow forking

        try {
            const response = await fetch(`/api/prompt/${encodeURIComponent(name)}`);
            if (!response.ok) return;

            const data = await response.json();
            // Update the textarea
            promptText.value = data.text || '';

        } catch (err) {
            console.error('Failed to load prompt:', err);
        }
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
