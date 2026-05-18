document.addEventListener('DOMContentLoaded', () => {
    // Authentication Check
    const token = localStorage.getItem('token');
    const role = localStorage.getItem('role');
    
    if (!token) {
        window.location.href = 'login.html';
        return; // Stop execution if not logged in
    }
    
    if (role === 'customer') {
        window.location.href = 'customer.html';
        return;
    }

    const navItems = document.querySelectorAll('.nav-item');
    const viewSections = document.querySelectorAll('.view-section');
    const pageTitle = document.getElementById('current-page-title');

    navItems.forEach(item => {
        item.addEventListener('click', (e) => {
            e.preventDefault();

            // Remove active class from all nav items and views
            navItems.forEach(nav => nav.classList.remove('active'));
            viewSections.forEach(view => view.classList.remove('active'));

            // Add active class to clicked nav item
            item.classList.add('active');

            // Get target view ID
            const targetId = item.getAttribute('data-target');
            const targetView = document.getElementById(targetId);

            // Add active class to target view
            if (targetView) {
                targetView.classList.add('active');
            }

            // Update Page Title
            const titleText = item.querySelector('span').textContent;
            pageTitle.textContent = titleText;
        });
    });

    // Logout logic
    const userProfile = document.querySelector('.user-profile');
    if (userProfile) {
        userProfile.style.cursor = 'pointer';
        userProfile.title = 'Click to logout';
        userProfile.addEventListener('click', () => {
            if (confirm('Are you sure you want to log out?')) {
                localStorage.removeItem('token');
                window.location.href = 'login.html';
            }
        });
    }

    // OpenAI Chat Logic
    const chatInput = document.querySelector('.chat-input-area input');
    const chatMessagesContainer = document.querySelector('.chat-messages');

    if (chatInput && chatMessagesContainer) {
        chatInput.addEventListener('keypress', async (e) => {
            if (e.key === 'Enter' && chatInput.value.trim() !== '') {
                const userMsg = chatInput.value.trim();
                chatInput.value = '';

                // Add user message to UI
                addMessageToUI(userMsg, 'outgoing');

                // Add loading indicator
                const loadingId = addMessageToUI('...', 'incoming');

                try {
                    const response = await fetch('/api/ai-chat', {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json',
                            'Authorization': `Bearer ${token}`
                        },
                        body: JSON.stringify({ message: userMsg })
                    });
                    
                    const data = await response.json();
                    
                    // Remove loading indicator
                    document.getElementById(loadingId).remove();

                    if (response.ok) {
                        addMessageToUI(data.reply, 'incoming');
                    } else {
                        addMessageToUI('Error: ' + (data.error || 'Failed to reach AI'), 'incoming');
                    }
                } catch (err) {
                    document.getElementById(loadingId).remove();
                    addMessageToUI('Connection error.', 'incoming');
                }
            }
        });
    }

    function addMessageToUI(text, type) {
        const msgDiv = document.createElement('div');
        msgDiv.className = `message ${type}`;
        const id = 'msg-' + Date.now();
        msgDiv.id = id;

        if (type === 'incoming') {
            msgDiv.innerHTML = `
                <div class="avatar">AI</div>
                <div class="bubble">${text}</div>
            `;
        } else {
            msgDiv.innerHTML = `<div class="bubble">${text}</div>`;
        }

        chatMessagesContainer.appendChild(msgDiv);
        chatMessagesContainer.scrollTop = chatMessagesContainer.scrollHeight;
        return id;
    }
});
