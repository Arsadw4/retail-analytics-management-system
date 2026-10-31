/**
 * csrf-delete.js
 *
 * Why this exists: several list pages had delete actions wired up as
 * plain GET links, e.g. <a href="/admin/delete-user/5">. A GET
 * request is not protected by Flask-WTF's CSRF check (by design --
 * GET should never mutate state), which means any external page
 * could trigger a delete just by getting a logged-in admin to load
 * an <img> or <a> pointing at that URL. This turns any element
 * marked `data-confirm-delete` into a real POST request carrying the
 * CSRF token, with a confirmation prompt before submitting.
 *
 * Usage in a template:
 *   <a href="#" class="delete-btn" data-confirm-delete="/admin/delete-user/5">Delete</a>
 * The corresponding Flask route must accept methods=["POST"] only.
 */
document.addEventListener("DOMContentLoaded", function () {
    var csrfToken = document.querySelector('meta[name="csrf-token"]');
    csrfToken = csrfToken ? csrfToken.getAttribute("content") : "";
    document.querySelectorAll("[data-confirm-delete]").forEach(function (el) {
        el.addEventListener("click", function (event) {
            event.preventDefault();
            var url = el.getAttribute("data-confirm-delete");
            var label = el.getAttribute("data-confirm-message") || "Delete this item? This cannot be undone.";
            if (!window.confirm(label)) {
                return;
            }
            var form = document.createElement("form");
            form.method = "POST";
            form.action = url;
            var tokenInput = document.createElement("input");
            tokenInput.type = "hidden";
            tokenInput.name = "csrf_token";
            tokenInput.value = csrfToken;
            form.appendChild(tokenInput);
            document.body.appendChild(form);
            form.submit();
        });
    });
});
