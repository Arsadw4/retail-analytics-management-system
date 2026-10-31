document.addEventListener("DOMContentLoaded", function () {
    document.querySelectorAll("[data-print]").forEach(function (el) {
        el.addEventListener("click", function (event) {
            event.preventDefault();
            window.print();
        });
    });
    document.querySelectorAll("[data-history-back]").forEach(function (el) {
        el.addEventListener("click", function (event) {
            event.preventDefault();
            history.back();
        });
    });
    document.querySelectorAll("[data-submit-form]").forEach(function (el) {
        el.addEventListener("change", function () {
            if (el.form) el.form.submit();
        });
    });
    document.querySelectorAll("[data-restore-source]").forEach(function (el) {
        function syncRestoreRows() {
            const upload = document.getElementById("upload-row");
            const existing = document.getElementById("existing-row");
            if (upload) upload.style.display = el.value === "upload" ? "block" : "none";
            if (existing) existing.style.display = el.value === "existing" ? "block" : "none";
        }
        el.addEventListener("change", syncRestoreRows);
        syncRestoreRows();
    });
    document.querySelectorAll("[data-focus-target]").forEach(function (el) {
        el.addEventListener("click", function () {
            const target = document.getElementById(el.getAttribute("data-focus-target"));
            target?.focus();
        });
    });
});
