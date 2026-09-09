import type { Metadata, Viewport } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "DiSản Lens — Chụp một chứng tích, mở một câu chuyện",
  description:
    "Khám phá câu chuyện lịch sử từ hình ảnh hiện vật bằng công nghệ nhận diện có trách nhiệm.",
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  themeColor: "#102a43",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="vi">
      <body>{children}</body>
    </html>
  );
}
