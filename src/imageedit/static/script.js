document.addEventListener('DOMContentLoaded', () => {
    initAutoSubmit();
    initLoadingStates();
    initConfirmations();
    initThemeToggle();
    initModelSizeSync();
    initDualInputs();
    initStyleControls();
    initImageSourceControls();
    initPromptControls();
    initShortcuts();
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

            const styleName = styleSelect.value.trim() || 'custom';
            const lines = promptTextarea.value.split(/\r?\n/);
            const styleIndex = lines.findIndex(line => line.startsWith('Style:'));
            const base = (styleIndex >= 0 ? lines.slice(0, styleIndex) : lines)
                .join('\n')
                .trimEnd();
            const styleBlock = `Style: ${styleName}\n${textToInsert}`;

            promptTextarea.value = base ? `${base}\n${styleBlock}` : styleBlock;
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
    const promptInput = document.getElementById('prompt-name-preset');
    const promptTextarea = document.getElementById('prompt-text');
    const loadPromptBtn = document.getElementById('load-prompt-btn');
    const savePromptBtn = document.getElementById('save-prompt-btn');
    const deletePromptBtn = document.getElementById('delete-prompt-btn');

    if (!promptInput || !promptTextarea) return;

    const hasPromptOption = (name) => {
        const listId = promptInput.getAttribute('list');
        if (!listId) return false;
        const list = document.getElementById(listId);
        if (!list) return false;
        return Array.from(list.options).some(option => option.value === name);
    };

    const loadPrompt = async (name) => {
        if (!name) {
            // If "New / Custom" (empty value) is selected, maybe leave as is?
            // For prompts, let's NOT clear the main textarea because user might be typing a "New" prompt.
            return;
        }
        if (!hasPromptOption(name)) return;

        try {
            const response = await fetch(`/api/prompt/${encodeURIComponent(name)}`);
            if (response.ok) {
                const data = await response.json();
                promptTextarea.value = data.text || '';
            }
        } catch (err) {
            console.error('Failed to load prompt:', err);
        }
    };

    // 1. Load Prompt Button
    if (loadPromptBtn) {
        loadPromptBtn.addEventListener('click', async (e) => {
            e.preventDefault();
            await loadPrompt(promptInput.value);
        });
    }

    // 2. Save Prompt Button
    if (savePromptBtn) {
        const modal = document.getElementById('save-prompt-modal');
        const confirmBtn = document.getElementById('confirm-save-prompt-btn');
        const cancelBtn = document.getElementById('cancel-prompt-btn');
        const nameInput = document.getElementById('new-prompt-name');
        const messageContainer = document.querySelector('.messages');

        const closeModal = () => {
            modal.classList.remove('active');
            nameInput.value = '';
        };

        const showMessage = (type, text) => {
            if (!messageContainer) return;
            messageContainer.innerHTML = '';
            const message = document.createElement('p');
            message.className = type;
            message.textContent = text;
            messageContainer.appendChild(message);
        };

        const openModal = () => {
            const textToSave = promptTextarea.value.trim();
            if (!textToSave) {
                alert('Please enter some prompt text to save.');
                return;
            }

            // Pre-populate name if a preset is selected
            const currentName = promptInput.value;
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
                        const savedName = data.saved_name || name;
                        showMessage('status', `Prompt saved as "${savedName}"`);
                        promptInput.value = savedName;
                        const list = document.getElementById('prompt-options');
                        if (list && !Array.from(list.options).some(option => option.value === savedName)) {
                            const option = document.createElement('option');
                            option.value = savedName;
                            list.appendChild(option);
                        }
                    } else {
                        const errData = await response.json();
                        showMessage('error', 'Error saving prompt: ' + (errData.error || 'Unknown error'));
                    }
                } catch (err) {
                    console.error('Save failed:', err);
                    showMessage('error', 'Failed to save prompt.');
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
            const name = promptInput.value;
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

            const name = promptInput.value;
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

function initShortcuts() {
    const modal = document.getElementById('shortcuts-modal');
    const closeBtn = document.getElementById('close-shortcuts-btn');
    const loadBtn = document.getElementById('load-prompt-btn');
    const saveBtn = document.getElementById('save-prompt-btn');
    const duplicateBtn = document.getElementById('duplicate-prompt-btn');
    const generateBtn = document.querySelector('button[name="action"][value="run"]');
    const promptTextarea = document.getElementById('prompt-text');
    const modelSelect = document.getElementById('model-name');
    const sizeSelect = document.getElementById('image-size-preset');
    const styleSelect = document.getElementById('style-name-preset');
    const insertStyleBtn = document.getElementById('insert-style-btn');

    if (!modal) return;

    const closeModal = () => {
        modal.classList.remove('active');
    };

    const openModal = () => {
        modal.classList.add('active');
    };

    if (closeBtn) {
        closeBtn.addEventListener('click', closeModal);
    }

    modal.addEventListener('click', (e) => {
        if (e.target === modal) closeModal();
    });

    document.addEventListener('keydown', (e) => {
        const key = e.key;
        const active = document.activeElement;
        const tag = active?.tagName?.toLowerCase();
        const isTyping = tag === 'input' || tag === 'textarea' || tag === 'select' || active?.isContentEditable;

        if (key === '?' || (key === '/' && e.shiftKey)) {
            if (modal.classList.contains('active')) {
                closeModal();
            } else {
                openModal();
            }
            e.preventDefault();
            return;
        }

        if (key === 'Escape' && modal.classList.contains('active')) {
            closeModal();
            return;
        }

        if (isTyping) return;

        if (key === 'l') {
            if (loadBtn) loadBtn.click();
            e.preventDefault();
        } else if (key === 's') {
            if (saveBtn) saveBtn.click();
            e.preventDefault();
        } else if (key === 'd') {
            if (duplicateBtn) duplicateBtn.click();
            e.preventDefault();
        } else if (key === 'g') {
            if (generateBtn) generateBtn.click();
            e.preventDefault();
        } else if (key === 'p') {
            if (promptTextarea) promptTextarea.focus();
            e.preventDefault();
        } else if (key === 'm') {
            if (modelSelect) modelSelect.focus();
            e.preventDefault();
        } else if (key === 'D') {
            if (sizeSelect) sizeSelect.focus();
            e.preventDefault();
        } else if (key === 'S') {
            if (styleSelect) styleSelect.focus();
            e.preventDefault();
        } else if (key === 'I') {
            if (insertStyleBtn) insertStyleBtn.click();
            e.preventDefault();
        }
    });
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

                const response = await fetch('/api/upload', {
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

    urls.forEach((url, index) => {
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
                <button type="button" class="delete-btn" title="Remove">×</button>
            `;
            // Re-attach listener to the new button inside error div
            const btn = item.querySelector('.delete-btn');
            if (btn) btn.onclick = () => removeUrl(index);
        };

        const deleteBtn = document.createElement('button');
        deleteBtn.type = 'button';
        deleteBtn.className = 'delete-btn';
        deleteBtn.innerHTML = '×';
        deleteBtn.title = 'Remove';
        deleteBtn.onclick = (e) => {
            e.stopPropagation(); // Prevent bubbling if needed
            removeUrl(index);
        };

        item.appendChild(img);
        item.appendChild(deleteBtn);
        container.appendChild(item);
    });

    function removeUrl(indexToRemove) {
        // Remove item at index
        urls.splice(indexToRemove, 1);
        // Update textarea
        const newText = urls.join('\n');
        document.getElementById('image-urls').value = newText;
        // Re-render
        renderImagePreviews(newText, container);
    }
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
        'gallery-height'
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

    let hideTimer = null;

    const triggerFlash = (element) => {
        element.classList.remove('flash-attention');
        void element.offsetWidth;
        element.classList.add('flash-attention');
    };

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
                if (hideTimer) {
                    clearTimeout(hideTimer);
                    hideTimer = null;
                }

                const isHidden = getComputedStyle(urlsGroup).display === 'none';
                if (supportsUrls) {
                    urlsGroup.style.display = 'block';
                    triggerFlash(urlsGroup);
                } else if (!isHidden) {
                    triggerFlash(urlsGroup);
                    hideTimer = setTimeout(() => {
                        urlsGroup.style.display = 'none';
                        urlsGroup.classList.remove('flash-attention');
                        hideTimer = null;
                    }, 900);
                }
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
