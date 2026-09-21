(function () {
  function isChinesePage() {
    return window.location.pathname.split("/").filter(Boolean)[0] === "zh";
  }

  function labels() {
    return isChinesePage()
      ? { copy: "复制", copied: "已复制" }
      : { copy: "Copy", copied: "Copied" };
  }

  function copyText(text) {
    if (navigator.clipboard && window.isSecureContext) {
      return navigator.clipboard.writeText(text);
    }
    var input = document.createElement("textarea");
    input.value = text;
    input.setAttribute("readonly", "");
    input.style.position = "fixed";
    input.style.left = "-9999px";
    document.body.appendChild(input);
    input.select();
    document.execCommand("copy");
    document.body.removeChild(input);
    return Promise.resolve();
  }

  function init() {
    var text = labels();
    document.querySelectorAll(".rst-content pre").forEach(function (pre) {
      if (pre.parentElement.classList.contains("code-copy-wrapper")) return;
      var wrapper = document.createElement("div");
      wrapper.className = "code-copy-wrapper";
      pre.parentNode.insertBefore(wrapper, pre);
      wrapper.appendChild(pre);
      var button = document.createElement("button");
      button.type = "button";
      button.className = "code-copy-btn";
      button.textContent = text.copy;
      button.addEventListener("click", function () {
        copyText((pre.querySelector("code") || pre).innerText.replace(/
$/, "")).then(function () {
          button.textContent = text.copied;
          button.classList.add("copied");
          window.setTimeout(function () {
            button.textContent = text.copy;
            button.classList.remove("copied");
          }, 1600);
        });
      });
      wrapper.appendChild(button);
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
