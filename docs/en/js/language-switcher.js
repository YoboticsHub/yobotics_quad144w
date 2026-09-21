(function () {
  function stripLanguage(inputPath) {
    return (inputPath || "").replace(/^(zh|en)\//, "");
  }

  function htmlPathFromInput(inputPath) {
    var path = stripLanguage(inputPath);
    if (!path) {
      return "index.html";
    }
    return path.replace(/\.md$/, ".html");
  }

  function currentOutputPath(isChinese, htmlPath) {
    return (isChinese ? "zh/" : "") + htmlPath;
  }

  function targetOutputPath(isChinese, htmlPath) {
    return (isChinese ? "" : "zh/") + htmlPath;
  }

  function relativePath(fromFile, toFile) {
    var fromParts = fromFile.split("/").slice(0, -1).filter(Boolean);
    var toParts = toFile.split("/").filter(Boolean);
    var common = 0;

    while (
      common < fromParts.length &&
      common < toParts.length &&
      fromParts[common] === toParts[common]
    ) {
      common += 1;
    }

    var up = fromParts.slice(common).map(function () {
      return "..";
    });
    var down = toParts.slice(common);
    var result = up.concat(down).join("/");
    return result || "index.html";
  }

  function languageState() {
    var inputPath = window.mkdocs_page_input_path || "";
    var isChinese = inputPath.indexOf("zh/") === 0;

    if (!inputPath) {
      isChinese = window.location.pathname.indexOf("/zh/") !== -1;
    }

    return {
      isChinese: isChinese,
      htmlPath: htmlPathFromInput(inputPath),
    };
  }

  function insertSwitcher() {
    var state = languageState();
    var fromFile = currentOutputPath(state.isChinese, state.htmlPath);
    var toFile = targetOutputPath(state.isChinese, state.htmlPath);
    var href = relativePath(fromFile, toFile);
    var label = state.isChinese ? "English" : "中文";
    var title = state.isChinese ? "Switch to English" : "切换到中文";
    var search = document.querySelector(".wy-side-nav-search");

    if (!search || search.querySelector(".language-switcher")) {
      return;
    }

    var wrapper = document.createElement("div");
    wrapper.className = "language-switcher";

    var link = document.createElement("a");
    link.className = "language-switcher-link language-switcher__link";
    link.href = href;
    link.textContent = label;
    link.setAttribute("aria-label", title);
    link.setAttribute("title", title);

    wrapper.appendChild(link);
    search.appendChild(wrapper);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", insertSwitcher);
  } else {
    insertSwitcher();
  }
})();
