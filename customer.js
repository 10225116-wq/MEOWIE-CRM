document.addEventListener('DOMContentLoaded', () => {
    // 1. Auth & Role Verification
    const token = localStorage.getItem('token');
    const role = localStorage.getItem('role');
    
    if (!token) {
        window.location.href = 'login.html';
        return;
    }
    
    if (role === 'manager') {
        window.location.href = 'index.html';
        return;
    }

    // 2. Tab Navigation Logic
    const navTabs = document.querySelectorAll('.nav-tab[data-target]');
    const tabContents = document.querySelectorAll('.mobile-tab-content');

    navTabs.forEach(tab => {
        tab.addEventListener('click', () => {
            // Remove active classes
            navTabs.forEach(t => t.classList.remove('active'));
            tabContents.forEach(c => c.classList.remove('active'));

            // Add active to clicked tab
            tab.classList.add('active');
            
            // Show corresponding content
            const targetId = tab.getAttribute('data-target');
            document.getElementById(targetId).classList.add('active');
        });
    });

    // 3. Profile & Logout Logic
    const btnPersonalInfo = document.getElementById('btn-personal-info');
    const btnBackToProfile = document.getElementById('btn-back-to-profile');
    const profileMainMenu = document.getElementById('profile-main-menu');
    const profileDetails = document.getElementById('profile-details');
    const btnTogglePassword = document.getElementById('btn-toggle-password');
    const infoPassword = document.getElementById('info-password');
    
    const logoutTrigger = document.getElementById('btn-logout-trigger');
    const logoutModal = document.getElementById('logout-confirm-modal');
    const btnConfirmLogout = document.getElementById('btn-confirm-logout');
    const btnCancelLogout = document.getElementById('btn-cancel-logout');

    // Dynamic greeting & profile data load
    const usernameVal = localStorage.getItem('username') || 'demo_customer';
    const roleVal = localStorage.getItem('role') || 'customer';
    const passwordVal = localStorage.getItem('password') || '123456789';

    const greetingText = document.getElementById('profile-greeting-text');
    if (greetingText) greetingText.textContent = `Hey, ${usernameVal}!`;

    if (btnPersonalInfo && profileMainMenu && profileDetails) {
        btnPersonalInfo.addEventListener('click', () => {
            // Load fresh info
            document.getElementById('info-name').textContent = usernameVal;
            document.getElementById('info-role').textContent = roleVal.charAt(0).toUpperCase() + roleVal.slice(1);
            infoPassword.value = passwordVal;
            
            profileMainMenu.classList.add('hidden');
            profileDetails.classList.remove('hidden');
        });
    }

    if (btnBackToProfile && profileMainMenu && profileDetails) {
        btnBackToProfile.addEventListener('click', () => {
            profileMainMenu.classList.remove('hidden');
            profileDetails.classList.add('hidden');
        });
    }

    if (btnTogglePassword && infoPassword) {
        btnTogglePassword.addEventListener('click', () => {
            if (infoPassword.type === 'password') {
                infoPassword.type = 'text';
                btnTogglePassword.innerHTML = '<i class="fa-regular fa-eye-slash"></i>';
            } else {
                infoPassword.type = 'password';
                btnTogglePassword.innerHTML = '<i class="fa-regular fa-eye"></i>';
            }
        });
    }

    // Modal triggers
    if (logoutTrigger && logoutModal) {
        logoutTrigger.addEventListener('click', () => {
            logoutModal.classList.remove('hidden');
        });
    }

    if (btnCancelLogout && logoutModal) {
        btnCancelLogout.addEventListener('click', () => {
            logoutModal.classList.add('hidden');
        });
    }

    if (btnConfirmLogout) {
        btnConfirmLogout.addEventListener('click', () => {
            localStorage.removeItem('token');
            localStorage.removeItem('role');
            localStorage.removeItem('username');
            localStorage.removeItem('password');
            window.location.href = 'login.html';
        });
    }

    // 4. OpenAI Chat Logic (Meowie CRM Bot)
    const chatInput = document.getElementById('mobile-chat-input');
    const chatContainer = document.getElementById('chat-messages-container');

    if (chatInput && chatContainer) {
        chatInput.addEventListener('keypress', async (e) => {
            if (e.key === 'Enter' && chatInput.value.trim() !== '') {
                const userMsg = chatInput.value.trim();
                chatInput.value = '';

                // Add user msg to UI
                addMobileMessage(userMsg, 'outgoing');

                // Add typing indicator
                const loadingId = addMobileMessage('...', 'incoming');

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
                    document.getElementById(loadingId).remove();

                    if (response.ok) {
                        addMobileMessage(data.reply, 'incoming');
                    } else {
                        addMobileMessage('Error: ' + (data.error || 'Connection failed'), 'incoming');
                    }
                } catch (err) {
                    document.getElementById(loadingId).remove();
                    addMobileMessage('Connection error.', 'incoming');
                }
            }
        });
    }

    let msgCounter = 0;
    function addMobileMessage(text, type) {
        const msgDiv = document.createElement('div');
        msgDiv.className = `msg-mobile ${type}`;
        const id = 'msg-' + Date.now() + '-' + (++msgCounter);
        msgDiv.id = id;
        msgDiv.textContent = text;

        chatContainer.appendChild(msgDiv);
        chatContainer.scrollTop = chatContainer.scrollHeight;
        return id;
    }
});
