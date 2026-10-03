import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { FeaturedDiscoveries } from "@/components/featured-discoveries";
import { Museum360Experience } from "@/components/museum-360-experience";

describe("museum discovery sections", () => {
  it("opens Route 1C by default and switches to official HCMC Museum scenes", async () => {
    const user = userEvent.setup();
    render(<Museum360Experience />);

    expect(screen.queryByTitle(/Tham quan 360 độ/)).not.toBeInTheDocument();
    expect(
      screen.getByRole("link", { name: /Xem 360 trên website/ }),
    ).toHaveAttribute("href", "https://duong1c.apptgs.vn/");

    expect(screen.getByRole("button", { name: "Con đường 1C" })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    expect(screen.getByRole("button", { name: "Hồi niệm" })).toBeVisible();
    expect(
      screen.getByRole("button", { name: "Đấu tranh 1930–1954" }),
    ).toBeVisible();
    expect(
      screen.getByRole("button", { name: "Địa lý – Hành chính" }),
    ).toBeVisible();
    expect(
      screen.getByRole("button", { name: "Dấu ấn Võ Văn Kiệt" }),
    ).toBeVisible();
    expect(
      screen.getByRole("button", { name: "Ký ức Mậu Thân 1968" }),
    ).toBeVisible();

    await user.click(
      screen.getByRole("button", { name: "Toàn cảnh bảo tàng" }),
    );

    expect(
      screen.getByRole("link", { name: /Xem 360 trên website/ }),
    ).toHaveAttribute("href", expect.stringContaining("startscene=scene_view_2"));
    expect(
      screen.getByRole("link", {
        name: "Bảo tàng Thành phố Hồ Chí Minh — tham quan trực tuyến",
      }),
    ).toHaveAttribute("href", "https://hcmc-museum.edu.vn/");
    expect(screen.getByRole("link", { name: "StarGlobal3D" })).toHaveAttribute(
      "href",
      "https://starglobal3d.com/smart-museum-360",
    );

    const rooms = [
      {
        button: "Đấu tranh 1930–1954",
        title: "Đấu tranh cách mạng 1930–1954",
        scene: "scene_01-phong-dau-tranh-cach-mang-(7)",
      },
      {
        button: "Địa lý – Hành chính",
        title: "Địa lý – Hành chính Thành phố Hồ Chí Minh",
        scene: "scene_02_phong_dia_ly_hanh_chinh_(6)",
      },
      {
        button: "Dấu ấn Võ Văn Kiệt",
        title: "Dấu ấn Thủ tướng Võ Văn Kiệt",
        scene: "scene_01_phong_dau_an_thu_tuong_vo_van_kiet_(1)",
      },
      {
        button: "Ký ức Mậu Thân 1968",
        title: "55 năm Ký ức Mậu Thân 1968",
        scene: "scene_06_trien_lam_55_nam_ky_uc_mau_than_(1)",
      },
    ];

    for (const room of rooms) {
      await user.click(screen.getByRole("button", { name: room.button }));

      const expectedUrl =
        `https://sanpham.starglobal3d.com/smart-museum-3d/hcmc-museum/` +
        `?startscene=${room.scene}`;

      expect(
        screen.getByRole("link", { name: /Xem 360 trên website/ }),
      ).toHaveAttribute("href", expectedUrl);
      expect(
        screen.getByRole("link", { name: /Xem 360 trên website/ }),
      ).not.toHaveAttribute("href", expect.stringContaining("%28"));
    }
  });

  it("shows four curated images and opens the selected artifact", async () => {
    const user = userEvent.setup();
    const onSelect = vi.fn();
    render(<FeaturedDiscoveries onSelect={onSelect} />);

    expect(screen.getAllByRole("img")).toHaveLength(4);
    await user.click(
      screen.getByRole("button", {
        name: "Khám phá Tượng Bà mẹ bằng mảnh bom",
      }),
    );
    expect(onSelect).toHaveBeenCalledWith("tuong-ba-me-bang-manh-bom");
    expect(
      screen.getByRole("link", { name: /Xem kho ảnh tư liệu chính thức/ }),
    ).toHaveAttribute(
      "href",
      "https://baotangchungtichchientranh.vn/vi/kham-pha/anh-tu-lieu",
    );
  });
});
