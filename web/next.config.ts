import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // 静态导出 — 整个 UI 打包成 HTML/CSS/JS, 无需 Node server.
  // 所有数据通过浏览器 fetch 走 API 后端 (CORS 已全开).
  // 部署: Vercel / Netlify / nginx / 任意静态托管, 一行命令.
  output: "export",
  // 静态导出时不优化图片
  images: { unoptimized: true },
  // 关掉 Next 自带的 trailingSlash 行为避免 url 重定向
  trailingSlash: true,
};

export default nextConfig;
