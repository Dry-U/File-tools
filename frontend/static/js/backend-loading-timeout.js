// 后端加载超时检测
// 90 秒后若加载指示器仍在显示，提示用户并提供"重试"按钮
// 通过外部 JS 文件加载以符合 CSP（避免 inline script 限制）
setTimeout(function () {
    var loading = document.getElementById('backend-loading');
    if (loading && loading.style.display !== 'none') {
        var tip = document.getElementById('backend-loading-tip');
        if (tip) {
            tip.innerHTML = '启动似乎遇到了问题，请检查后端服务是否正常运行。<br>'
                + '<button id="backend-retry-btn" style="margin-top:12px;padding:8px 20px;'
                + 'background:var(--llama-accent);color:#fff;border:none;border-radius:6px;'
                + 'cursor:pointer;font-size:13px;">重试</button>';
            var retryBtn = document.getElementById('backend-retry-btn');
            if (retryBtn) {
                retryBtn.addEventListener('click', function () {
                    location.reload();
                });
            }
        }
    }
}, 90000);
