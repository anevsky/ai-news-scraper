// Theme switcher for light/dark/auto mode with three icons
(function() {
    const toggle = document.getElementById('themeToggle');
    const html = document.documentElement;
    const lightIcon = document.getElementById('lightIcon');
    const darkIcon = document.getElementById('darkIcon');
    const autoIcon = document.getElementById('autoIcon');

    // Get saved theme or default to 'auto'
    const savedTheme = localStorage.getItem('theme') || 'auto';

    // Function to update icon visibility
    function updateIcon(theme) {
        // Hide all icons first
        if (lightIcon) lightIcon.classList.add('hidden');
        if (darkIcon) darkIcon.classList.add('hidden');
        if (autoIcon) autoIcon.classList.add('hidden');

        // Show the appropriate icon
        if (theme === 'light' && lightIcon) {
            lightIcon.classList.remove('hidden');
        } else if (theme === 'dark' && darkIcon) {
            darkIcon.classList.remove('hidden');
        } else if (autoIcon) {
            autoIcon.classList.remove('hidden');
        }
    }

    // Function to apply theme
    function applyTheme(theme) {
        if (theme === 'dark') {
            html.setAttribute('data-theme', 'dark');
        } else if (theme === 'light') {
            html.setAttribute('data-theme', 'light');
        } else {
            // Auto mode - follow system preference
            const prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
            html.setAttribute('data-theme', prefersDark ? 'dark' : 'light');
        }
        updateIcon(theme);
    }

    // Apply saved theme on load
    applyTheme(savedTheme);

    // Handle toggle click - cycles through auto -> light -> dark -> auto
    if (toggle) {
        toggle.addEventListener('click', function() {
            const currentTheme = localStorage.getItem('theme') || 'auto';
            let newTheme;

            // Cycle through themes
            if (currentTheme === 'auto') {
                newTheme = 'light';
            } else if (currentTheme === 'light') {
                newTheme = 'dark';
            } else {
                newTheme = 'auto';
            }

            localStorage.setItem('theme', newTheme);
            applyTheme(newTheme);
        });
    }

    // Listen for system theme changes when in auto mode
    window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', (e) => {
        const theme = localStorage.getItem('theme') || 'auto';
        if (theme === 'auto') {
            html.setAttribute('data-theme', e.matches ? 'dark' : 'light');
            // Keep showing auto icon since we're still in auto mode
            updateIcon('auto');
        }
    });
})();
