import type { NextConfig } from "next";

const gatewayProxyTarget =
  process.env.GATEWAY_PROXY_TARGET || "http://127.0.0.1:8080";

const nextConfig: NextConfig = {
  async rewrites() {
    return [
      {
        source: "/api/:path*",
        destination: `${gatewayProxyTarget}/api/:path*`,
      },
      {
        source: "/ws",
        destination: `${gatewayProxyTarget}/ws`,
      },
    ];
  },
};

export default nextConfig;
