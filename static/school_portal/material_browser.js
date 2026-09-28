(function () {
    "use strict";
    var modes = ["extra-large", "large", "medium", "small", "list", "details", "tiles", "content"];
    var storageKey = "schoolportal.materials.view";
    var browser = document.querySelector(".materials-browser");
    if (!browser) return;

    function valid(mode) { return modes.indexOf(mode) !== -1; }
    function updateLinks(mode) {
        document.querySelectorAll("[data-material-link]").forEach(function (link) {
            var url = new URL(link.href, window.location.origin);
            url.searchParams.set("view", mode);
            link.href = url.pathname + url.search + url.hash;
        });
    }
    function setMode(mode, persist) {
        if (!valid(mode)) return;
        document.documentElement.dataset.materialsView = mode;
        browser.className = browser.className.replace(/\bview-[a-z-]+\b/g, "").trim() + " view-" + mode;
        document.querySelectorAll("[data-view-mode]").forEach(function (button) {
            button.setAttribute("aria-pressed", String(button.dataset.viewMode === mode));
        });
        updateLinks(mode);
        if (persist) {
            try { window.localStorage.setItem(storageKey, mode); } catch (error) {}
        }
        var url = new URL(window.location.href);
        url.searchParams.set("view", mode);
        window.history.replaceState(null, "", url.pathname + url.search + url.hash);
    }

    var initialMode = document.documentElement.dataset.materialsView;
    setMode(valid(initialMode) ? initialMode : "tiles", false);
    document.querySelectorAll("[data-view-mode]").forEach(function (button) {
        button.addEventListener("click", function () { setMode(button.dataset.viewMode, true); });
    });

    var sortState = { key: "name", ascending: true };
    var container = browser.querySelector(".materials-items");
    document.querySelectorAll("[data-sort-key]").forEach(function (button) {
        button.addEventListener("click", function () {
            var key = button.dataset.sortKey;
            sortState.ascending = sortState.key === key ? !sortState.ascending : true;
            sortState.key = key;
            Array.from(container.children).sort(function (left, right) {
                if (left.dataset.folder !== right.dataset.folder) return left.dataset.folder === "1" ? -1 : 1;
                var a = left.dataset[key] || "";
                var b = right.dataset[key] || "";
                var comparison;
                if (key === "size" || key === "modified") comparison = Number(a || -1) - Number(b || -1);
                else comparison = a.localeCompare(b, "ar", { sensitivity: "base" });
                return sortState.ascending ? comparison : -comparison;
            }).forEach(function (item) { container.appendChild(item); });
            document.querySelectorAll("[data-sort-key]").forEach(function (header) {
                header.setAttribute("aria-sort", header === button ? (sortState.ascending ? "ascending" : "descending") : "none");
            });
        });
    });
}());
