import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  reactStrictMode: true,
  poweredByHeader: false,
  async headers() {
    return [
      {
        source: "/:path*",
        headers: [
          { key: "X-Content-Type-Options", value: "nosniff" },
          { key: "X-Frame-Options", value: "DENY" },
          { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
          {
            key: "Permissions-Policy",
            value:
              'camera=(self), microphone=(), geolocation=(), fullscreen=(self "https://btctct.apptgs.vn" "https://duong1c.apptgs.vn" "https://sanpham.starglobal3d.com"), accelerometer=(self "https://btctct.apptgs.vn" "https://duong1c.apptgs.vn" "https://sanpham.starglobal3d.com"), gyroscope=(self "https://btctct.apptgs.vn" "https://duong1c.apptgs.vn" "https://sanpham.starglobal3d.com")',
          },
        ],
      },
    ];
  },
};

export default nextConfig;
