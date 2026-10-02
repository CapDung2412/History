"use client";

import { useState } from "react";
import { ArrowIcon, RotateIcon } from "@/components/icons";

type VirtualTour = {
  id: string;
  museum: string;
  shortTitle: string;
  title: string;
  description: string;
  tourUrl: string;
  sourceUrl: string;
  sourceLabel: string;
};

type VirtualTourGroup = {
  museum: string;
  tours: VirtualTour[];
};

const HCMC_MUSEUM_TOUR_URL =
  "https://sanpham.starglobal3d.com/smart-museum-3d/hcmc-museum/";

function hcmcMuseumScene(scene: string) {
  // The remote krpano viewer compares `startscene` with its scene names before
  // decoding percent-encoded parentheses. Keep those characters literal so a
  // room such as `...(7)` is found instead of falling back to scene 0.
  return `${HCMC_MUSEUM_TOUR_URL}?startscene=${encodeURIComponent(scene)}`;
}

const TOUR_GROUPS: VirtualTourGroup[] = [
  {
    museum: "Bảo tàng Chứng tích Chiến tranh",
    tours: [
      {
        id: "duong-1c",
        museum: "Bảo tàng Chứng tích Chiến tranh",
        shortTitle: "Con đường 1C",
        title: "Thời thanh xuân trên tuyến đường 1C huyền thoại",
        description:
          "Bước vào không gian trưng bày 360° về tuyến đường 1C và những thanh niên đã vận chuyển người, vũ khí, hàng hóa trên tuyến chi viện chiến lược này trong chiến tranh.",
        tourUrl: "https://duong1c.apptgs.vn/",
        sourceUrl:
          "https://www.baotangchungtichchientranh.vn/vi/trung-bay-va-su-kien/trung-bay/thoi-thanh-xuan-tren-tuyen-duong-1c-huyen-thoai",
        sourceLabel:
          "Bảo tàng Chứng tích Chiến tranh — Thời thanh xuân trên tuyến đường 1C huyền thoại",
      },
      {
        id: "hoi-niem",
        museum: "Bảo tàng Chứng tích Chiến tranh",
        shortTitle: "Hồi niệm",
        title: "Hồi niệm",
        description:
          "Di chuyển giữa các điểm nhìn của trưng bày “Hồi niệm”, xoay toàn cảnh và quan sát cách những hình ảnh, tư liệu cùng hiện vật kể lại ký ức chiến tranh.",
        tourUrl: "https://btctct.apptgs.vn/",
        sourceUrl:
          "https://baotangchungtichchientranh.vn/vi/trung-bay-va-su-kien/trung-bay/hoi-niem",
        sourceLabel:
          "Bảo tàng Chứng tích Chiến tranh — trưng bày Hồi niệm",
      },
    ],
  },
  {
    museum: "Bảo tàng Thành phố Hồ Chí Minh",
    tours: [
      {
        id: "hcmc-toan-canh",
        museum: "Bảo tàng Thành phố Hồ Chí Minh",
        shortTitle: "Toàn cảnh bảo tàng",
        title: "Toàn cảnh Bảo tàng Thành phố Hồ Chí Minh",
        description:
          "Quan sát kiến trúc, khuôn viên và bắt đầu hành trình qua các tầng trưng bày của Bảo tàng Thành phố Hồ Chí Minh từ một điểm nhìn toàn cảnh.",
        tourUrl: hcmcMuseumScene("scene_view_2"),
        sourceUrl: "https://hcmc-museum.edu.vn/",
        sourceLabel: "Bảo tàng Thành phố Hồ Chí Minh — tham quan trực tuyến",
      },
      {
        id: "hcmc-dau-tranh-cach-mang",
        museum: "Bảo tàng Thành phố Hồ Chí Minh",
        shortTitle: "Đấu tranh 1930–1954",
        title: "Đấu tranh cách mạng 1930–1954",
        description:
          "Khám phá phòng trưng bày về phong trào đấu tranh cách mạng tại Sài Gòn – Chợ Lớn trong giai đoạn 1930–1954 qua các điểm nhìn 360°.",
        tourUrl: hcmcMuseumScene("scene_01-phong-dau-tranh-cach-mang-(7)"),
        sourceUrl: "https://hcmc-museum.edu.vn/",
        sourceLabel: "Bảo tàng Thành phố Hồ Chí Minh — tham quan trực tuyến",
      },
      {
        id: "hcmc-dia-ly-hanh-chinh",
        museum: "Bảo tàng Thành phố Hồ Chí Minh",
        shortTitle: "Địa lý – Hành chính",
        title: "Địa lý – Hành chính Thành phố Hồ Chí Minh",
        description:
          "Tham quan phòng Địa lý – Hành chính để tìm hiểu không gian tự nhiên, địa giới và quá trình hình thành diện mạo đô thị Thành phố Hồ Chí Minh.",
        tourUrl: hcmcMuseumScene("scene_02_phong_dia_ly_hanh_chinh_(6)"),
        sourceUrl: "https://hcmc-museum.edu.vn/",
        sourceLabel: "Bảo tàng Thành phố Hồ Chí Minh — tham quan trực tuyến",
      },
      {
        id: "hcmc-vo-van-kiet",
        museum: "Bảo tàng Thành phố Hồ Chí Minh",
        shortTitle: "Dấu ấn Võ Văn Kiệt",
        title: "Dấu ấn Thủ tướng Võ Văn Kiệt",
        description:
          "Khám phá không gian chuyên đề lưu giữ hình ảnh, tư liệu và dấu ấn hoạt động của Thủ tướng Võ Văn Kiệt trong lịch sử thành phố và đất nước.",
        tourUrl: hcmcMuseumScene(
          "scene_01_phong_dau_an_thu_tuong_vo_van_kiet_(1)",
        ),
        sourceUrl: "https://hcmc-museum.edu.vn/",
        sourceLabel: "Bảo tàng Thành phố Hồ Chí Minh — tham quan trực tuyến",
      },
      {
        id: "hcmc-mau-than-1968",
        museum: "Bảo tàng Thành phố Hồ Chí Minh",
        shortTitle: "Ký ức Mậu Thân 1968",
        title: "55 năm Ký ức Mậu Thân 1968",
        description:
          "Đi qua không gian triển lãm tái hiện ký ức về cuộc Tổng tiến công và nổi dậy Xuân Mậu Thân 1968 bằng tư liệu, hình ảnh và các điểm quan sát 360°.",
        tourUrl: hcmcMuseumScene(
          "scene_06_trien_lam_55_nam_ky_uc_mau_than_(1)",
        ),
        sourceUrl: "https://hcmc-museum.edu.vn/",
        sourceLabel: "Bảo tàng Thành phố Hồ Chí Minh — tham quan trực tuyến",
      },
    ],
  },
];

const TOURS = TOUR_GROUPS.flatMap((group) => group.tours);

export function Museum360Experience() {
  const [activeTourId, setActiveTourId] = useState("duong-1c");
  const activeTour =
    TOURS.find((tour) => tour.id === activeTourId) ?? TOURS[0];

  return (
    <section
      className="virtual-tour-section"
      id="tham-quan-360"
      aria-labelledby="virtual-tour-title"
    >
      <div className="site-shell virtual-tour-layout">
        <div
          className="virtual-tour-frame"
          id="virtual-tour-viewer"
          role="region"
          aria-label={`Trình xem 360°: ${activeTour.title}`}
        >
          <iframe
            key={activeTour.id}
            src={activeTour.tourUrl}
            title={`Tham quan 360 độ ${activeTour.title} tại ${activeTour.museum}`}
            loading="lazy"
            allow="fullscreen; accelerometer; gyroscope"
            allowFullScreen
            referrerPolicy="strict-origin-when-cross-origin"
          />
          <span className="virtual-tour-badge">
            <RotateIcon /> 360°
          </span>
        </div>

        <div className="virtual-tour-copy">
          <p className="eyebrow eyebrow-light">Bước vào không gian di sản</p>
          <h2 id="virtual-tour-title">Chọn hành trình tham quan 360°</h2>
          <p>
            Khám phá tuyến đường 1C và nhiều phòng trưng bày tiêu biểu của hai
            bảo tàng. Chọn một không gian bên dưới rồi kéo trên ảnh để quan sát
            toàn cảnh.
          </p>

          <div className="virtual-tour-picker">
            {TOUR_GROUPS.map((group) => (
              <div className="virtual-tour-group" key={group.museum}>
                <p>{group.museum}</p>
                <div role="group" aria-label={`Không gian của ${group.museum}`}>
                  {group.tours.map((tour) => {
                    const isActive = tour.id === activeTour.id;
                    return (
                      <button
                        className="virtual-tour-option"
                        type="button"
                        key={tour.id}
                        aria-pressed={isActive}
                        aria-controls="virtual-tour-viewer"
                        onClick={() => setActiveTourId(tour.id)}
                      >
                        <RotateIcon />
                        <span>{tour.shortTitle}</span>
                      </button>
                    );
                  })}
                </div>
              </div>
            ))}
          </div>

          <div className="virtual-tour-details" aria-live="polite">
            <p>{activeTour.museum}</p>
            <h3>{activeTour.title}</h3>
            <p>{activeTour.description}</p>
          </div>

          <div className="virtual-tour-actions">
            <a
              className="button button-cream button-large"
              href={activeTour.tourUrl}
              target="_blank"
              rel="noopener noreferrer"
              aria-describedby="virtual-tour-note"
            >
              <RotateIcon />
              Mở trong tab mới
              <ArrowIcon />
            </a>
          </div>
          <p className="virtual-tour-note" id="virtual-tour-note">
            Có thể kéo để xoay, chạm các điểm dẫn đường hoặc mở tour trong tab
            mới nếu màn hình điện thoại quá nhỏ.
          </p>
          <p className="virtual-tour-source">
            Nguồn: {" "}
            <a
              href={activeTour.sourceUrl}
              target="_blank"
              rel="noopener noreferrer"
            >
              {activeTour.sourceLabel}
            </a>
            .
          </p>
        </div>
      </div>
    </section>
  );
}
