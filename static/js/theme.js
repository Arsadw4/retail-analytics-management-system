(function () {
    const buttons = document.querySelectorAll('[data-theme-toggle]');
    const key = 'ra_theme';
    function apply(theme) {
        const isDark = theme === 'dark';
        document.documentElement.dataset.theme = isDark ? 'dark' : 'light';
        document.body.classList.toggle('dark-theme', isDark);
        buttons.forEach(button => {
            button.classList.toggle('is-dark', isDark);
            button.setAttribute('aria-pressed', isDark ? 'true' : 'false');
        });
        document.querySelectorAll('.menu-theme-icon').forEach(icon => {
            icon.textContent = isDark ? '☀' : '☾';
        });
        window.dispatchEvent(new CustomEvent('ra-theme-changed', {
            detail: {
                dark:isDark
            }
        }));
    }
    const saved = localStorage.getItem(key);
    const defaultTheme = document.body.classList.contains('app-shell') ? 'dark' : 'light';
    apply(saved === 'dark' || (!saved && defaultTheme === 'dark') ? 'dark' : 'light');
    buttons.forEach(button => button.addEventListener('click', function () {
        const next = document.body.classList.contains('dark-theme') ? 'light' : 'dark';
        localStorage.setItem(key, next);
        apply(next);
    }));
})();
