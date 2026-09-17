(function () {
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
    document.querySelectorAll(".rst-content pre").forEach(function (pre) {
      if (pre.parentElement.classList.contains("code-copy-wrapper")) return;
      var wrapper = document.createElement("div");
      wrapper.className = "code-copy-wrapper";
      pre.parentNode.insertBefore(wrapper, pre);
      wrapper.appendChild(pre);
      var button = document.createElement("button");
      button.type = "button";
      button.className = "code-copy-btn";
      button.textContent = "复制";
      button.addEventListener("click", function () {
        copyText((pre.querySelector("code") || pre).innerText.replace(/\n$/, "")).then(function () {
          button.textContent = "已复制";
          button.classList.add("copied");
          window.setTimeout(function () {
            button.textContent = "复制";
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
