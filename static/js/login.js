document.addEventListener('DOMContentLoaded', () => {
    const password = document.getElementById('password');
    const toggle = document.getElementById('passwordToggle');
    const form = document.querySelector('.login-form');
    const button = document.getElementById('loginButton');
    if (password && toggle) {
        toggle.addEventListener('click', () => {
            const visible = password.type === 'text';
            password.type = visible ? 'password' : 'text';
            toggle.setAttribute('aria-label', visible ? 'Show password' : 'Hide password');
            toggle.textContent = visible ? '◉' : '◌';
        });
    }
    if (form && button) {
        form.addEventListener('submit', () => {
            button.disabled = true;
            button.querySelector('span:first-child').textContent = 'Signing in...';
        });
    }
});
