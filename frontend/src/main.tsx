/* @refresh reload */
import { render } from "solid-js/web";
import App from "./App";
import "./styles/global.css";

const root = document.getElementById("root");

if (!root) {
  throw new Error("未找到根节点");
}

try {
  render(() => <App />, root);
} catch (e) {
  console.error("Render error:", e);
  root.innerHTML =
    '<div style="display:flex;height:100%;align-items:center;justify-content:center;padding:24px;color:#666;font:14px/1.6 -apple-system, BlinkMacSystemFont, \'Segoe UI\', sans-serif;">应用渲染失败，请打开控制台查看详细信息。</div>';
}

if (import.meta.env.DEV) {
  window.addEventListener("error", (e) => {
    console.error("Unhandled error:", e.error);
  });

  window.addEventListener("unhandledrejection", (e) => {
    console.error("Unhandled rejection:", e.reason);
  });
}
